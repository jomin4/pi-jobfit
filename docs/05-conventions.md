# 05. 개발 규약

> 이전 ← [04-roadmap.md](04-roadmap.md) · 다음 → [06-glossary.md](06-glossary.md)

---

## 1. 디렉터리 구조 (최종 형태)

```
pi-recruitment-notice/
├── docs/                         설계 문서 (진실의 원천)
├── data/                         시드 데이터 (스킬 사전, 평가셋) — Git 추적
├── notebooks/                    EDA / 실험 노트북
├── scripts/                      일회성 운영 스크립트
├── migrations/                   Alembic
│   └── versions/
├── src/jobfit/
│   ├── __init__.py
│   ├── config.py                 pydantic-settings 설정
│   ├── logging.py                structlog 설정
│   ├── db/
│   │   ├── base.py               SQLAlchemy Base / 엔진 / 세션
│   │   └── models.py             ORM 모델
│   ├── collectors/               [P1] 외부 데이터 수집
│   ├── processing/               [P1] 정규화 (Polars)
│   ├── skills/                   [P1] 스킬 추출
│   ├── matching/                 [P2] 피처 / 학습 / 스코어링
│   ├── embedding/                [P3] 청킹 / 임베딩 / 벡터검색
│   ├── rag/                      [P4] 리트리버 / 체인 / 평가
│   ├── agents/                   [P6] LangGraph
│   ├── mcp_server/               [P6] MCP 도구 서버
│   ├── worker/                   Celery 앱 + 태스크
│   └── api/                      FastAPI
│       ├── main.py
│       ├── deps.py
│       ├── middleware.py
│       ├── schemas/              Pydantic 요청/응답 모델
│       └── routers/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
├── infra/
│   ├── docker/                   Dockerfile 들
│   ├── prometheus/
│   ├── grafana/
│   └── k3s/                      [P7] k8s 매니페스트
├── airflow/                      [P7]
│   └── dags/
├── .github/workflows/
├── docker-compose.yml
├── .env.example
├── pyproject.toml
├── CLAUDE.md
└── README.md
```

**핵심 원칙**: `src/jobfit/` 안의 도메인 모듈은 **FastAPI에도, Celery에도, Airflow에도, 노트북에도** 그대로 import 된다.
프레임워크는 껍데기, 로직은 코어에.

---

## 2. 코딩 규약

| 항목 | 규칙 |
|---|---|
| Python | 3.12 고정 (`.python-version`, Docker 이미지 모두) |
| 포매터/린터 | `ruff format` + `ruff check` (line-length 100) |
| 타입 | `mypy --strict` 지향. public 함수는 타입 힌트 필수 |
| 네이밍 | 모듈/함수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER_SNAKE` |
| DB 컬럼 | `snake_case`, 불리언은 `is_`/`has_` 접두 |
| 시각 | 저장은 UTC(`TIMESTAMPTZ`), 표시 시 KST 변환 |
| 예외 | 도메인 예외는 `jobfit.exceptions`에 정의, API 레이어에서 HTTP로 변환 |
| 순수성 | 변환/계산 함수는 I/O 없이 순수하게. I/O는 호출부에서 주입 |
| 매직넘버 | 금지. `config.py` 또는 모듈 상수로 |
| 주석 | "무엇"이 아니라 "왜"를 적는다 |

### 함수 시그니처 패턴
```python
# 좋음: 순수 함수 — 테스트 쉬움
def parse_salary(raw: str) -> SalaryRange | None: ...


# 좋음: I/O는 의존성 주입
def upsert_jobs(session: Session, jobs: list[JobCreate]) -> int: ...


# 나쁨: 함수 내부에서 DB 연결을 직접 생성
def parse_and_save(raw: str): ...
```

---

## 3. Git 규약

### 브랜치
```
main            항상 배포 가능 상태
feat/p1-collector      Phase-작업 단위 브랜치
fix/salary-parsing
```

### 커밋 메시지 (Conventional Commits)
```
feat(collector): 고용24 목록 API 페이징 수집 구현
fix(normalize): 급여 "만원" 단위 파싱 오류 수정
docs(arch): 벡터 인덱스 선택 근거 추가
chore(ci): mypy 단계 추가
test(skills): 한글 조사 엣지케이스 추가
refactor(matching): 피처 계산을 순수 함수로 분리
```
타입: `feat` `fix` `docs` `test` `refactor` `chore` `perf`

### 규칙
- 커밋 1개 = 논리적 변경 1개
- `.env`, 모델 가중치, 대용량 데이터는 커밋 금지 (`.gitignore`)
- Phase 종료 시 태그: `v0.1.0-phase1`

---

## 4. 환경변수 (.env)

```ini
# App
APP_ENV=local                 # local | prod
LOG_LEVEL=INFO

# Database
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=jobfit
POSTGRES_USER=jobfit
POSTGRES_PASSWORD=changeme

# Redis
REDIS_URL=redis://localhost:6379/0

# External API (Phase 1)
WORK24_API_KEY=
WORK24_BASE_URL=

# ML (Phase 2)
MLFLOW_TRACKING_URI=http://localhost:5000

# Embedding (Phase 3)
EMBEDDING_MODEL=intfloat/multilingual-e5-small
EMBEDDING_DIM=384

# LLM (Phase 4)
LLM_PROVIDER=anthropic        # anthropic | ollama
LLM_MODEL=
LLM_API_KEY=

# Observability (Phase 5)
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=jobfit

# Auth (Phase 6)
JWT_SECRET_KEY=
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

규칙:
- `.env`는 절대 커밋 금지. `.env.example`만 커밋 (값은 비움)
- 모든 설정은 `src/jobfit/config.py`의 `Settings` 클래스를 통해서만 접근
- 운영 시크릿은 GitHub Secrets → k8s Secret으로 전달

---

## 5. 테스트 규약

| 종류 | 위치 | 대상 | 실행 |
|---|---|---|---|
| 단위 | `tests/unit/` | 순수 함수 (파싱/피처/청킹) | 매 커밋, 빠름 |
| 통합 | `tests/integration/` | DB/Redis 필요 로직 | CI, compose로 의존성 기동 |
| 평가 | `scripts/eval_*.py` | 모델/검색/RAG 품질 | Phase 종료 시 수동 |

- 외부 API는 **절대 실제 호출하지 않는다**. `tests/fixtures/`의 저장된 응답으로 모킹
- 테스트 이름은 한글 허용: `def test_경력_무관_공고는_exp_min이_0이다():`
- 커버리지 목표: 핵심 로직 60%+

---

## 6. 성능/안정성 가드레일

| 항목 | 규칙 |
|---|---|
| DB 쿼리 | N+1 금지. `selectinload`/`joinedload` 사용 |
| 배치 크기 | 임베딩 32, DB UPSERT 500건 단위 |
| 외부 API | 타임아웃 필수(connect 5s / read 30s), 재시도 3회 지수 백오프 |
| Celery | 태스크는 멱등하게. `acks_late=True`, `max_retries` 명시 |
| 메모리 | 전체 공고를 한 번에 메모리에 올리지 않는다 (스트리밍/청크 처리) |
| LLM | 토큰 예산 명시, 응답 타임아웃, 실패 시 graceful degradation |

---

## 7. 문서 갱신 규칙

- 설계를 바꾸면 **코드보다 문서를 먼저** 고친다.
- 각 Phase 종료 시 `docs/` 에 회고 1편 추가: `docs/retro-phaseN.md`
  - 무엇을 만들었나 / 수치 결과 / 막혔던 지점 / 다음에 다르게 할 것
- 이 회고가 나중에 포트폴리오·기술블로그의 원재료가 된다.
