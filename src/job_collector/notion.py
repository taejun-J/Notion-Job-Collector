from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .models import Job
from .normalize import normalize_url


AUTOMATION_MANAGED_PROPERTIES = frozenset(
    {
        "공고명", "External Job ID", "공고 URL", "공고 출처", "등록 방식",
        "기업", "포지션", "직무 카테고리", "근무지", "고용형태", "신입/경력",
        "공고 게시일", "지원 마감일", "수집일", "마지막 확인일", "주요 기술",
        "주요 업무", "필수 조건", "우대 조건", "적합도", "공고 활성 상태",
    }
)

USER_MANAGED_PROPERTIES = frozenset(
    {
        "지원 상태", "관심도", "지원일", "전형 예정일", "다음 할 일",
        "자기소개서 상태", "이력서 버전", "부족한 역량", "지원 이유", "메모",
        "결과", "면접 준비",
    }
)


def _text(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value[:2000]}}]}


def _title(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value[:2000]}}]}


def _select(value: str) -> dict[str, Any] | None:
    return {"select": {"name": value}} if value else None


def _multi(values: list[str]) -> dict[str, Any]:
    return {"multi_select": [{"name": value} for value in values]}


def _date(value: str | None) -> dict[str, Any] | None:
    return {"date": {"start": value}} if value else None


def _without_empty(properties: dict[str, dict[str, Any] | None]) -> dict[str, dict[str, Any]]:
    return {key: value for key, value in properties.items() if value is not None}


def build_automation_properties(job: Job, company_page_id: str | None = None) -> dict[str, Any]:
    properties = _without_empty(
        {
            "공고명": _title(job.title),
            "External Job ID": _text(job.external_job_id) if job.external_job_id else None,
            "공고 URL": {"url": normalize_url(job.url)},
            "공고 출처": _select(job.source),
            "등록 방식": _select("자동수집"),
            "기업": {"relation": [{"id": company_page_id}]} if company_page_id else None,
            "포지션": _text(job.position),
            "직무 카테고리": _multi(job.categories),
            "근무지": _text(job.location) if job.location else None,
            "고용형태": _select(job.employment_type),
            "신입/경력": _select(job.experience_level),
            "공고 게시일": _date(job.posted_date),
            "지원 마감일": _date(job.deadline),
            "수집일": _date(job.collected_date),
            "마지막 확인일": _date(job.last_checked_date),
            "주요 기술": _multi(job.technologies),
            "주요 업무": _text(job.responsibilities) if job.responsibilities else None,
            "필수 조건": _text(job.requirements) if job.requirements else None,
            "우대 조건": _text(job.preferred_qualifications) if job.preferred_qualifications else None,
            "적합도": {"number": job.fit_score} if job.fit_score is not None else None,
            "공고 활성 상태": _select(job.active_status),
        }
    )
    unexpected = set(properties) - AUTOMATION_MANAGED_PROPERTIES
    if unexpected:
        raise AssertionError(f"Unsafe automation properties: {sorted(unexpected)}")
    return properties


def build_create_properties(job: Job, company_page_id: str | None = None) -> dict[str, Any]:
    properties = build_automation_properties(job, company_page_id)
    properties["지원 상태"] = _select("관심")
    return properties


@dataclass(slots=True)
class UpsertResult:
    action: str
    page_id: str
    title: str


class NotionClient:
    def __init__(
        self,
        token: str,
        job_data_source_id: str,
        companies_data_source_id: str,
        api_version: str = "2026-03-11",
    ) -> None:
        self.token = token
        self.job_data_source_id = job_data_source_id
        self.companies_data_source_id = companies_data_source_id
        self.api_version = api_version

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"https://api.notion.com/v1{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": self.api_version,
                "Content-Type": "application/json",
                "User-Agent": "notion-job-collector/0.1",
            },
        )
        for attempt in range(4):
            try:
                with urlopen(request, timeout=30) as response:  # nosec B310: fixed HTTPS origin
                    return json.load(response)
            except HTTPError as error:
                if error.code == 429 and attempt < 3:
                    delay = float(error.headers.get("Retry-After", "1"))
                    time.sleep(max(delay, 1.0))
                    continue
                detail = error.read().decode("utf-8", errors="replace")
                raise RuntimeError(f"Notion API {error.code}: {detail}") from error
        raise RuntimeError("Notion API retry limit exceeded")

    def _query_first(self, data_source_id: str, filter_: dict[str, Any]) -> dict[str, Any] | None:
        result = self._request(
            "POST",
            f"/data_sources/{data_source_id}/query",
            {"filter": filter_, "page_size": 1, "result_type": "page"},
        )
        return result.get("results", [None])[0] if result.get("results") else None

    def find_job(self, job: Job) -> dict[str, Any] | None:
        if job.external_job_id:
            match = self._query_first(
                self.job_data_source_id,
                {
                    "and": [
                        {"property": "External Job ID", "rich_text": {"equals": job.external_job_id}},
                        {"property": "공고 출처", "select": {"equals": job.source}},
                    ]
                },
            )
            if match:
                return match
        return self._query_first(
            self.job_data_source_id,
            {"property": "공고 URL", "url": {"equals": normalize_url(job.url)}},
        )

    def upsert_company(self, name: str) -> str | None:
        if not name:
            return None
        existing = self._query_first(
            self.companies_data_source_id,
            {"property": "기업명", "title": {"equals": name}},
        )
        if existing:
            return str(existing["id"])
        created = self._request(
            "POST",
            "/pages",
            {
                "parent": {"type": "data_source_id", "data_source_id": self.companies_data_source_id},
                "properties": {"기업명": _title(name)},
            },
        )
        return str(created["id"])

    def upsert_job(self, job: Job) -> UpsertResult:
        existing = self.find_job(job)
        company_page_id = self.upsert_company(job.company)
        if existing:
            page_id = str(existing["id"])
            self._request(
                "PATCH",
                f"/pages/{page_id}",
                {"properties": build_automation_properties(job, company_page_id)},
            )
            return UpsertResult("updated", page_id, job.title)

        created = self._request(
            "POST",
            "/pages",
            {
                "parent": {"type": "data_source_id", "data_source_id": self.job_data_source_id},
                "properties": build_create_properties(job, company_page_id),
            },
        )
        return UpsertResult("created", str(created["id"]), job.title)

