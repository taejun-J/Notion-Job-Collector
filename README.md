# Notion Job Collector

채용 공고를 자동으로 모아 `Career Hub > Job Opportunities`에 안전하게 upsert하는 Python 프로젝트입니다.

핵심 안전 규칙:

- `External Job ID + 공고 출처`를 우선 중복키로 사용합니다.
- ID가 없으면 추적 파라미터를 제거한 `공고 URL`을 사용합니다.
- 기존 공고 갱신 시 자동화 관리 속성만 전송합니다.
- `지원 상태`, `관심도`, `지원일`, `다음 할 일`, `메모`, `결과` 등은 덮어쓰지 않습니다.
- 새 공고에만 `지원 상태=관심`을 초기화합니다.

## 1. Notion 연결

1. Notion 개발자 페이지에서 Internal Integration을 생성합니다.
2. `Career Hub`에서 아래 두 데이터베이스를 integration과 공유합니다.
   - Job Opportunities
   - Companies
3. 토큰을 로컬 `.env` 또는 GitHub Actions의 `NOTION_TOKEN` Secret에 저장합니다.

데이터 소스 ID는 이미 프로젝트에 설정되어 있습니다.

| 용도 | Data source ID |
|---|---|
| Job Opportunities | `fe880847-c020-4c66-b8d4-840cfa4bbb6a` |
| Companies | `95eedd44-631c-4f96-a18e-08f470709d96` |

## 2. 로컬 검증

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
collect-jobs --input sample/jobs.sample.json --dry-run
```

실제 Notion 쓰기:

```bash
export NOTION_TOKEN="secret_..."
collect-jobs --input sample/jobs.sample.json
```

샘플을 실제로 실행하면 `[SAMPLE]` 레코드 두 개(기업·공고)가 생성되므로, 먼저 `--dry-run` 사용을 권장합니다.

## 3. 입력 JSON 규격

최상위 배열 또는 `{ "jobs": [...] }` 형식을 받습니다.

필수 필드:

- `title`, `company`, `position`, `source`, `url`

주요 선택 필드:

- `external_job_id`
- `categories`
- `location`, `employment_type`, `experience_level`
- `posted_date`, `deadline`
- `technologies`
- `responsibilities`, `requirements`, `preferred_qualifications`
- `fit_score` — 자동으로 0~100 범위로 제한

한글 Property 이름을 키로 넣어도 대부분 동일하게 인식합니다. 전체 예시는 `sample/jobs.sample.json`을 참고하세요.

## 4. GitHub Actions

1. 이 폴더를 GitHub 저장소에 push합니다.
2. Repository secret `NOTION_TOKEN`을 등록합니다.
3. Repository variable `JOB_FEED_URL`에 공개 JSON feed URL을 등록합니다.
4. Actions에서 `Collect jobs to Notion`을 수동 실행해 검증합니다.
5. 이후 매일 07:17 KST에 자동 실행됩니다.

사이트별 HTML 크롤러는 이용약관·robots.txt·페이지 구조가 서로 다르므로 이 기반 프로젝트에 어댑터로 추가해야 합니다. 첫 실제 수집처를 정하면 해당 사이트 전용 파서를 연결할 수 있습니다.

## API 기준

Notion API `2026-03-11`을 사용합니다. 인증 토큰은 `Authorization: Bearer` 헤더로 전달하며, 공고 조회는 Data Source Query, 생성은 Data Source 부모를 가진 Page Create, 갱신은 Page Update를 사용합니다.
