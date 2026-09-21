from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from .models import Job


JASOSEOL_CALENDAR_URL = "https://jasoseol.com/employment/calendar_list.json"
JASOSEOL_DUTY_GROUPS_URL = "https://jasoseol.com/api/v1/duty-groups"
JASOSEOL_RECRUIT_URL = "https://jasoseol.com/recruit/{job_id}"
JASOSEOL_IT_DUTY_ROOT = "IT·인터넷"

# 공개 달력에 표시되는 공고명/직무명만 대상으로 분류한다.
# 상세 공고 이미지 OCR이나 로그인 세션은 사용하지 않는다.
CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "IT": ("it",),
    "IT Infra": (
        "it infra", "infrastructure", "인프라", "it 운영", "it운영",
    ),
    "Cloud": ("cloud", "클라우드", "aws", "azure", "gcp"),
    "DevOps": ("devops", "dev ops", "데브옵스", "ci/cd", "배포 자동화"),
    "SRE": ("sre", "site reliability"),
    "Backend": (
        "backend", "back-end", "백엔드", "server engineer", "서버 개발",
        "data engineer", "데이터 엔지니어", "software engineer", "소프트웨어 엔지니어",
    ),
    "IT/OT": ("it/ot", "ot 보안", "smart factory", "스마트팩토리"),
    "Platform": ("platform", "플랫폼"),
    "System Engineer": (
        "system engineer", "system administrator", "시스템 엔지니어", "시스템 운영",
    ),
    "IT Planning": ("it planning", "it 기획", "it기획"),
    "Network": ("network", "네트워크"),
    "Security": ("security", "cyber", "보안", "정보보호"),
}

TARGET_CATEGORIES = frozenset(
    {"IT", "IT Infra", "Cloud", "DevOps", "Backend", "IT/OT", "Platform", "System Engineer", "IT Planning"}
)

TECHNOLOGY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "AWS": ("aws",),
    "Cloud": ("cloud", "클라우드", "azure", "gcp", "google cloud"),
    "Infrastructure": ("infra", "infrastructure", "인프라"),
    "Linux": ("linux", "리눅스"),
    "Docker": ("docker", "도커"),
    "Kubernetes": ("kubernetes", "k8s", "쿠버네티스"),
    "Terraform": ("terraform",),
    "GitHub Actions": ("github actions",),
    "Network": ("network", "네트워크"),
    "Database": ("database", "데이터베이스"),
    "DevOps": ("devops", "dev ops", "데브옵스"),
    "SRE": ("sre", "site reliability"),
    "Java": ("java",),
    "CI/CD": ("ci/cd",),
}

EXCLUDE_KEYWORDS = ("sales", "세일즈", "영업", "marketing", "마케팅")


def _month_bounds(today: date) -> tuple[str, str]:
    start = today.replace(day=1)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (
        f"{start.isoformat()}T00:00:00+09:00",
        f"{end.isoformat()}T00:00:00+09:00",
    )


def _seoul_today() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def _date_part(value: Any) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date().isoformat()
    except ValueError:
        return None


def _search_text(raw: dict[str, Any], duty_names: list[str] | None = None) -> str:
    fields = [str(raw.get("title", ""))]
    fields.extend(
        str(item.get("field", ""))
        for item in raw.get("employments") or []
        if isinstance(item, dict)
    )
    fields.extend(duty_names or [])
    return " ".join(fields).casefold()


def _contains(text: str, keyword: str) -> bool:
    needle = keyword.casefold()
    if re.fullmatch(r"[a-z0-9+#./ -]+", needle):
        return re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) is not None
    return needle in text


def _matching_labels(text: str, mapping: dict[str, tuple[str, ...]]) -> list[str]:
    return [label for label, words in mapping.items() if any(_contains(text, word) for word in words)]


def _matches_custom_keywords(text: str, keywords: list[str] | None) -> bool:
    return not keywords or any(_contains(text, keyword) for keyword in keywords)


def _division_values(employments: list[dict[str, Any]]) -> set[int]:
    divisions: set[int] = set()
    for employment in employments:
        raw = employment.get("division")
        values = raw if isinstance(raw, list) else [raw]
        divisions.update(int(value) for value in values if str(value).isdigit())
    return divisions


def _duty_group_ids(employments: list[dict[str, Any]]) -> list[int]:
    values: list[int] = []
    for employment in employments:
        for duty in employment.get("duty_groups") or []:
            if isinstance(duty, dict) and str(duty.get("group_id", "")).isdigit():
                value = int(duty["group_id"])
                if value not in values:
                    values.append(value)
    return values


def _duty_group_context(
    employments: list[dict[str, Any]], duty_groups: list[dict[str, Any]] | None
) -> tuple[list[str], bool]:
    if not duty_groups:
        return [], False
    by_id = {
        int(item["id"]): item
        for item in duty_groups
        if isinstance(item, dict) and str(item.get("id", "")).isdigit()
    }
    selected_ids = _duty_group_ids(employments)

    def ancestor_ids(duty_id: int) -> list[int]:
        result: list[int] = []
        current = by_id.get(duty_id)
        while current and str(current.get("group_id", "")).isdigit():
            parent_id = int(current["group_id"])
            result.append(parent_id)
            current = by_id.get(parent_id)
        return result

    it_selected_ids = [
        duty_id
        for duty_id in selected_ids
        if any(
            by_id.get(value, {}).get("name") == JASOSEOL_IT_DUTY_ROOT
            for value in [duty_id, *ancestor_ids(duty_id)]
        )
    ]
    parent_ids = {ancestor for duty_id in it_selected_ids for ancestor in ancestor_ids(duty_id)}
    names = [
        str(by_id[duty_id].get("name", "")).strip()
        for duty_id in it_selected_ids
        if duty_id in by_id and duty_id not in parent_ids
    ]
    return list(dict.fromkeys(name for name in names if name)), bool(it_selected_ids)


def _experience_level(employments: list[dict[str, Any]]) -> str:
    divisions = _division_values(employments)
    if 5 in divisions or 3 in divisions or {1, 2}.issubset(divisions):
        return "신입 가능"
    if divisions == {1}:
        return "신입"
    if divisions == {2}:
        return "경력"
    return "무관" if divisions else ""


def _employment_type(employments: list[dict[str, Any]]) -> str:
    values = _division_values(employments)
    if 3 in values and 4 in values:
        return "기타"
    if 3 in values:
        return "인턴"
    if 4 in values:
        return "계약직"
    return ""


def parse_calendar_payload(
    payload: dict[str, Any],
    *,
    today: date | None = None,
    keywords: list[str] | None = None,
    max_jobs: int = 300,
    duty_groups: list[dict[str, Any]] | None = None,
) -> list[Job]:
    """Convert active, relevant public calendar entries into Notion jobs."""
    today = today or _seoul_today()
    rows = payload.get("employment", [])
    if not isinstance(rows, list):
        raise ValueError("Unexpected Jasoseol calendar response: 'employment' is not a list")

    jobs: list[Job] = []
    seen: set[str] = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        job_id = str(raw.get("id", ""))
        start = _date_part(raw.get("start_time"))
        deadline = _date_part(raw.get("end_time"))
        if not job_id or not start or not deadline or not (start <= today.isoformat() <= deadline):
            continue

        employments = [item for item in raw.get("employments") or [] if isinstance(item, dict)]
        duty_names, is_it_duty = _duty_group_context(employments, duty_groups)
        text = _search_text(raw, duty_names)
        categories = _matching_labels(text, CATEGORY_KEYWORDS)
        if is_it_duty and "IT" not in categories:
            categories.insert(0, "IT")
        is_any_it_job = "IT" in categories or is_it_duty
        matches_profile = bool(set(categories) & (TARGET_CATEGORIES - {"IT"}))
        matches_profile = (
            matches_profile
            and not any(_contains(text, keyword) for keyword in EXCLUDE_KEYWORDS)
            and _matches_custom_keywords(text, keywords)
        )
        if not (is_any_it_job or matches_profile) or job_id in seen:
            continue

        positions = list(dict.fromkeys(str(item.get("field", "")).strip() for item in employments))
        positions = [value for value in positions if value]
        positions.extend(value for value in duty_names if value not in positions)
        title = str(raw.get("title", "")).strip()
        company = str(raw.get("name", "")).strip()
        if not title or not company:
            continue

        technologies = _matching_labels(text, TECHNOLOGY_KEYWORDS)
        fit_score = min(95.0, 60.0 + 8.0 * len(categories) + 3.0 * len(technologies))
        jobs.append(
            Job(
                title=title,
                company=company,
                position=" / ".join(positions) or title,
                source="자소설닷컴",
                url=JASOSEOL_RECRUIT_URL.format(job_id=job_id),
                external_job_id=job_id,
                categories=categories,
                employment_type=_employment_type(employments),
                experience_level=_experience_level(employments),
                posted_date=start,
                deadline=deadline,
                technologies=technologies,
                fit_score=fit_score,
                collected_date=today.isoformat(),
                last_checked_date=today.isoformat(),
            )
        )
        seen.add(job_id)

    jobs.sort(key=lambda job: (job.deadline or "9999-12-31", -float(job.fit_score or 0), job.company))
    return jobs[:max_jobs]


def load_jasoseol_jobs(
    *,
    today: date | None = None,
    keywords: list[str] | None = None,
    max_jobs: int = 300,
) -> list[Job]:
    """Load public calendar and duty taxonomy data without login or per-job requests."""
    today = today or _seoul_today()
    start_time, end_time = _month_bounds(today)
    body = json.dumps({"start_time": start_time, "end_time": end_time}).encode("utf-8")
    calendar_request = Request(
        JASOSEOL_CALENDAR_URL,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": "https://jasoseol.com",
            "Referer": "https://jasoseol.com/recruit",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/131.0 Safari/537.36"
            ),
        },
    )
    duty_groups_request = Request(
        JASOSEOL_DUTY_GROUPS_URL,
        headers={
            "Accept": "application/json",
            "Referer": "https://jasoseol.com/recruit",
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "Chrome/131.0 Safari/537.36"
            ),
        },
    )
    try:
        with urlopen(duty_groups_request, timeout=30) as response:  # nosec B310: fixed HTTPS origin
            duty_groups = json.load(response)
        with urlopen(calendar_request, timeout=30) as response:  # nosec B310: fixed HTTPS origin
            payload = json.load(response)
    except (HTTPError, URLError) as error:
        raise RuntimeError(
            "자소설닷컴 공개 달력 요청에 실패했습니다. 사이트 정책/구조가 바뀌었는지 확인하세요."
        ) from error
    if not isinstance(duty_groups, list):
        raise RuntimeError("자소설닷컴 직무 분류 응답 형식이 예상과 다릅니다.")
    return parse_calendar_payload(
        payload,
        today=today,
        keywords=keywords,
        max_jobs=max_jobs,
        duty_groups=duty_groups,
    )
