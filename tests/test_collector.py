import unittest

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


if __name__ == "__main__":
    unittest.main()

