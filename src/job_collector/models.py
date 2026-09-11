from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


def _items(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [str(part).strip() for part in value if str(part).strip()]


@dataclass(slots=True)
class Job:
    title: str
    company: str
    position: str
    source: str
    url: str
    external_job_id: str = ""
    categories: list[str] = field(default_factory=list)
    location: str = ""
    employment_type: str = ""
    experience_level: str = ""
    posted_date: str | None = None
    deadline: str | None = None
    technologies: list[str] = field(default_factory=list)
    responsibilities: str = ""
    requirements: str = ""
    preferred_qualifications: str = ""
    fit_score: float | None = None
    collected_date: str = field(default_factory=lambda: date.today().isoformat())
    last_checked_date: str = field(default_factory=lambda: date.today().isoformat())
    active_status: str = "모집중"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Job":
        aliases = {
            "title": raw.get("title") or raw.get("공고명"),
            "company": raw.get("company") or raw.get("기업"),
            "position": raw.get("position") or raw.get("포지션"),
            "source": raw.get("source") or raw.get("공고 출처"),
            "url": raw.get("url") or raw.get("공고 URL"),
        }
        missing = [key for key, value in aliases.items() if not value]
        if missing:
            raise ValueError(f"Missing required job fields: {', '.join(missing)}")

        score = raw.get("fit_score", raw.get("적합도"))
        if score is not None:
            score = max(0.0, min(100.0, float(score)))

        return cls(
            **aliases,
            external_job_id=str(raw.get("external_job_id", raw.get("External Job ID", ""))),
            categories=_items(raw.get("categories", raw.get("직무 카테고리"))),
            location=str(raw.get("location", raw.get("근무지", ""))),
            employment_type=str(raw.get("employment_type", raw.get("고용형태", ""))),
            experience_level=str(raw.get("experience_level", raw.get("신입/경력", ""))),
            posted_date=raw.get("posted_date", raw.get("공고 게시일")),
            deadline=raw.get("deadline", raw.get("지원 마감일")),
            technologies=_items(raw.get("technologies", raw.get("주요 기술"))),
            responsibilities=str(raw.get("responsibilities", raw.get("주요 업무", ""))),
            requirements=str(raw.get("requirements", raw.get("필수 조건", ""))),
            preferred_qualifications=str(raw.get("preferred_qualifications", raw.get("우대 조건", ""))),
            fit_score=score,
            collected_date=str(raw.get("collected_date", raw.get("수집일", date.today().isoformat()))),
            last_checked_date=str(raw.get("last_checked_date", raw.get("마지막 확인일", date.today().isoformat()))),
            active_status=str(raw.get("active_status", raw.get("공고 활성 상태", "모집중"))),
        )

