from __future__ import annotations

import argparse
import json
import os
import sys

from .feed import load_jobs
from .notion import NotionClient, build_create_properties


DEFAULT_JOB_DS = "fe880847-c020-4c66-b8d4-840cfa4bbb6a"
DEFAULT_COMPANY_DS = "95eedd44-631c-4f96-a18e-08f470709d96"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Upsert job postings into Notion Career Hub")
    result.add_argument("--input", default=os.getenv("JOB_FEED_URL", ""), help="JSON file path or public URL")
    result.add_argument("--dry-run", action="store_true", help="Validate and print payloads without Notion writes")
    return result


def main() -> None:
    args = parser().parse_args()
    if not args.input:
        raise SystemExit("Provide --input or set JOB_FEED_URL")

    jobs = load_jobs(args.input)
    if args.dry_run:
        for job in jobs:
            print(json.dumps(build_create_properties(job), ensure_ascii=False))
        print(f"Validated {len(jobs)} job(s)", file=sys.stderr)
        return

    token = os.getenv("NOTION_TOKEN", "")
    if not token:
        raise SystemExit("NOTION_TOKEN is required unless --dry-run is used")

    client = NotionClient(
        token=token,
        job_data_source_id=os.getenv("NOTION_JOB_DATA_SOURCE_ID", DEFAULT_JOB_DS),
        companies_data_source_id=os.getenv("NOTION_COMPANIES_DATA_SOURCE_ID", DEFAULT_COMPANY_DS),
        api_version=os.getenv("NOTION_API_VERSION", "2026-03-11"),
    )
    for job in jobs:
        result = client.upsert_job(job)
        print(f"{result.action}: {result.title} ({result.page_id})")


if __name__ == "__main__":
    main()

