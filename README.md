# Notion Job Collector

자소설닷컴의 공개 채용 달력에서 목표 직무 공고를 골라 `Career Hub > Job Opportunities`에 안전하게 upsert하는 Python 프로젝트입니다.

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
collect-jobs --source jasoseol --max-jobs 20 --dry-run
collect-jobs --source json --input sample/jobs.sample.json --dry-run
```

실제 Notion 쓰기:

```bash
export NOTION_TOKEN="secret_..."
collect-jobs --source jasoseol --max-jobs 50
```

JSON 샘플을 실제로 실행하면 `[SAMPLE]` 레코드 두 개(기업·공고)가 생성되므로, 먼저 `--dry-run` 사용을 권장합니다.

## 3. 자소설닷컴 수집 기준

- 로그인, 쿠키, 개인 계정 세션을 사용하지 않습니다.
- 공개 채용 달력 API를 실행당 한 번만 요청하고 상세 공고를 반복 조회하지 않습니다.
- 현재 모집 중인 공고만 남깁니다.
- 공고명과 공개 직무명에 `IT Infra`, `Cloud`, `DevOps`, `SRE`, `Backend`, `IT/OT`, `Platform`, `System Engineer`, `Network`, `Security` 관련 키워드가 있는 공고만 수집합니다.
- 적합도는 키워드 일치 개수에 따른 60~95점의 1차 휴리스틱입니다. 실제 검토 후 Notion의 관심도를 직접 기록하세요.
- `JASOSEOL_KEYWORDS` Repository variable에 쉼표 구분 키워드를 넣으면 기본 IT 필터를 통과한 공고를 추가로 좁힐 수 있습니다.
- 공개 API와 페이지 구조는 자소설닷컴의 공식 API 계약이 아니므로 변경 시 어댑터 수정이 필요할 수 있습니다.

예: `JASOSEOL_KEYWORDS=AWS,클라우드,인프라`

## 4. 입력 JSON 규격 (선택)

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

## 5. GitHub Actions

1. 이 폴더를 GitHub 저장소에 push합니다.
2. Repository secret `NOTION_TOKEN`을 등록합니다.
3. 선택 사항으로 Repository variable `JASOSEOL_KEYWORDS`를 등록합니다.
4. Actions에서 `Collect jobs to Notion`을 수동 실행해 검증합니다. 처음에는 `max_jobs=5`가 안전합니다.
5. 이후 매일 07:17 KST에 자동 실행됩니다.

GitHub Actions가 실패하면 로그에서 자소설닷컴 접근 오류인지 Notion 권한 오류인지 확인하세요. 수집처가 자동 접근 정책이나 응답 구조를 변경하면 스케줄을 중지하고 어댑터를 갱신해야 합니다.

## API 기준

Notion API `2026-03-11`을 사용합니다. 인증 토큰은 `Authorization: Bearer` 헤더로 전달하며, 공고 조회는 Data Source Query, 생성은 Data Source 부모를 가진 Page Create, 갱신은 Page Update를 사용합니다.
