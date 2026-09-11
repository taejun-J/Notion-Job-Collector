from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

from .models import Job


def load_jobs(location: str) -> list[Job]:
    if location.startswith(("https://", "http://")):
        request = Request(location, headers={"User-Agent": "notion-job-collector/0.1"})
        with urlopen(request, timeout=30) as response:  # nosec B310: explicit http(s) check above
            payload = json.load(response)
    else:
        payload = json.loads(Path(location).read_text(encoding="utf-8"))

    rows = payload.get("jobs", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("The feed must be a JSON array or an object with a 'jobs' array")
    return [Job.from_dict(row) for row in rows]

