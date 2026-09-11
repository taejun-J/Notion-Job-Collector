import unittest
from datetime import date

from job_collector.jasoseol import parse_calendar_payload
from job_collector.models import Job
from job_collector.normalize import normalize_url
from job_collector.notion import (
    USER_MANAGED_PROPERTIES,
    build_automation_properties,
    build_create_properties,
)


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.job = Job.from_dict(
            {
                "title": "Cloud Engineer",
                "company": "Example",
                "position": "Cloud Engineer",
                "source": "기타",
                "url": "https://EXAMPLE.com/jobs/1/?utm_source=x#details",
                "external_job_id": "1",
                "categories": ["Cloud"],
                "technologies": ["AWS"],
                "fit_score": 101,
            }
        )

    def test_normalize_url(self) -> None:
        self.assertEqual(normalize_url(self.job.url), "https://example.com/jobs/1")

    def test_fit_score_is_clamped(self) -> None:
        self.assertEqual(self.job.fit_score, 100.0)

    def test_update_payload_never_contains_user_fields(self) -> None:
        properties = build_automation_properties(self.job, "company-page")
        self.assertFalse(set(properties) & USER_MANAGED_PROPERTIES)

    def test_create_payload_initializes_status_only(self) -> None:
        properties = build_create_properties(self.job, "company-page")
        self.assertEqual(properties["지원 상태"]["select"]["name"], "관심")
        self.assertFalse((set(properties) & USER_MANAGED_PROPERTIES) - {"지원 상태"})

    def test_jasoseol_parser_keeps_only_active_matching_jobs(self) -> None:
        payload = {
            "employment": [
                {
                    "id": 101,
                    "name": "Example Cloud",
                    "title": "Cloud Platform Engineer 신입 채용",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [{"field": "DevOps Engineer", "division": [1]}],
                },
                {
                    "id": 102,
                    "name": "Example Sales",
                    "title": "영업 담당자 채용",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [{"field": "영업", "division": [2]}],
                },
                {
                    "id": 103,
                    "name": "Expired Infra",
                    "title": "IT Infra Engineer",
                    "start_time": "2026-08-01T00:00:00+09:00",
                    "end_time": "2026-09-01T23:59:00+09:00",
                    "employments": [{"field": "IT Infra", "division": [2]}],
                },
                {
                    "id": 104,
                    "name": "Example Sales",
                    "title": "Cloud Platform Sales",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [],
                },
            ]
        }
        jobs = parse_calendar_payload(payload, today=date(2026, 9, 11))
        self.assertEqual([job.external_job_id for job in jobs], ["101"])
        self.assertEqual(jobs[0].source, "자소설닷컴")
        self.assertEqual(jobs[0].experience_level, "신입")
        self.assertEqual(jobs[0].categories, ["Cloud", "DevOps", "Platform"])
        self.assertEqual(jobs[0].technologies, ["Cloud", "DevOps"])

    def test_jasoseol_custom_keyword_is_additional_filter(self) -> None:
        payload = {
            "employment": [
                {
                    "id": 201,
                    "name": "Example",
                    "title": "AWS Cloud Engineer",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [],
                }
            ]
        }
        jobs = parse_calendar_payload(payload, today=date(2026, 9, 11), keywords=["AWS"])
        self.assertEqual(jobs[0].external_job_id, "201")
        self.assertEqual(parse_calendar_payload(payload, today=date(2026, 9, 11), keywords=["Azure"]), [])


if __name__ == "__main__":
    unittest.main()
