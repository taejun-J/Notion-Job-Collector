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
                {
                    "id": 105,
                    "name": "Example IT",
                    "title": "IT Sales 담당자",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-20T23:59:00+09:00",
                    "employments": [],
                },
            ]
        }
        jobs = parse_calendar_payload(payload, today=date(2026, 9, 11))
        self.assertEqual({job.external_job_id for job in jobs}, {"101", "105"})
        self.assertEqual([job.external_job_id for job in jobs], ["105", "101"])
        cloud_job = next(job for job in jobs if job.external_job_id == "101")
        self.assertEqual(cloud_job.source, "자소설닷컴")
        self.assertEqual(cloud_job.experience_level, "신입")
        self.assertEqual(cloud_job.categories, ["Cloud", "DevOps", "Platform"])
        self.assertEqual(cloud_job.technologies, ["Cloud", "DevOps"])
        it_job = next(job for job in jobs if job.external_job_id == "105")
        self.assertEqual(it_job.categories, ["IT"])

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

    def test_jasoseol_uses_duty_group_taxonomy_for_generic_titles(self) -> None:
        duty_groups = [
            {"id": 91, "name": "경영·사무", "group_id": None, "category": "large"},
            {"id": 94, "name": "IT·인터넷", "group_id": None, "category": "large"},
            {"id": 103, "name": "기획·전략·경영", "group_id": 91, "category": "medium"},
            {"id": 162, "name": "웹개발", "group_id": 94, "category": "medium"},
            {"id": 176, "name": "서버·백엔드개발", "group_id": 162, "category": "small"},
        ]
        payload = {
            "employment": [
                {
                    "id": 301,
                    "name": "Example Group",
                    "title": "2026년 신입사원 공개채용",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [
                        {
                            "division": 1,
                            "duty_groups": [{"group_id": 162}, {"group_id": 176}],
                        }
                    ],
                },
                {
                    "id": 302,
                    "name": "Example Office",
                    "title": "2026년 신입사원 공개채용",
                    "start_time": "2026-09-01T00:00:00+09:00",
                    "end_time": "2026-09-30T23:59:00+09:00",
                    "employments": [{"division": 1, "duty_groups": [{"group_id": 103}]}],
                },
            ]
        }
        jobs = parse_calendar_payload(payload, today=date(2026, 9, 11), duty_groups=duty_groups)
        self.assertEqual([job.external_job_id for job in jobs], ["301"])
        self.assertEqual(jobs[0].position, "서버·백엔드개발")
        self.assertIn("IT", jobs[0].categories)
        self.assertIn("Backend", jobs[0].categories)


if __name__ == "__main__":
    unittest.main()
