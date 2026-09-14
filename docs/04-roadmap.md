# 04. 실행 로드맵 (Phase 0 ~ 7)

> 이전 ← [03-data-model.md](03-data-model.md) · 다음 → [05-conventions.md](05-conventions.md)
> 전제: 주 20시간+, 총 10~11주. 각 Phase는 **DoD를 전부 만족**해야 종료.

---

## 전체 일정

| Phase | 주제 | 기간 | 누적 |
|---|---|---|---|
| 0 | 기반 환경 · CI · 클라우드 | 1주 | 1주 |
| 1 | 데이터 파이프라인 (수집→정규화→스킬) | 2주 | 3주 |
| 2 | ML 매칭 모델 + MLflow | 1.5주 | 4.5주 |
| 3 | 임베딩 · 벡터 검색 | 1주 | 5.5주 |
| 4 | RAG + FastAPI + RAGAS 평가 | 2주 | 7.5주 |
| 5 | 관측성 (Prometheus/Grafana/LangSmith) | 0.5주 | 8주 |
| 6 | 에이전트 (LangGraph/MCP) + 인증 | 1.5주 | 9.5주 |
| 7 | Airflow · k3s 배포 · LLM 서빙 | 1.5주 | 11주 |

---

## Phase 0 — 기반 환경 (1주)

**목표**: 명령 하나로 전체 개발 환경이 뜨고, push 하면 CI가 검증하고, 클라우드에 배포 대상 서버가 준비된 상태.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 0.1 | Git 저장소 초기화 + GitHub 원격 연결 | `.gitignore`, 첫 커밋 |
| 0.2 | Python 3.12 가상환경 + `pyproject.toml` | `pyproject.toml`, `.python-version` |
| 0.3 | 프로젝트 디렉터리 스캐폴드 | `src/jobfit/...` |
| 0.4 | `docker-compose.yml`: postgres(pgvector) + redis | 컨테이너 기동 |
| 0.5 | 설정 관리 `pydantic-settings` + `.env.example` | `src/jobfit/config.py` |
| 0.6 | SQLAlchemy 2.0 엔진 + Alembic 초기화 | `migrations/` |
| 0.7 | FastAPI 헬스체크 `/health` (DB/Redis 연결 확인) | `src/jobfit/api/main.py` |
| 0.8 | 개발 도구: ruff, mypy, pytest, pre-commit | `.pre-commit-config.yaml` |
| 0.9 | GitHub Actions: lint → typecheck → test → docker build | `.github/workflows/ci.yml` |
| 0.10 | Oracle Cloud 가입 + Always Free ARM 인스턴스 생성 + SSH | 서버 접속 확인 |

### DoD
- [ ] `docker compose up -d` 후 `/health` 가 db/redis 모두 ok 반환
- [ ] `alembic upgrade head` 성공 (빈 리비전이라도)
- [ ] GitHub에 push → Actions 초록불
- [ ] Oracle ARM 인스턴스에 SSH 접속 + `docker --version` 확인

### 학습 포인트
컨테이너 네트워킹 / 12-factor 설정 / 마이그레이션의 의미 / CI 파이프라인 구조

---

## Phase 1 — 데이터 파이프라인 (2주)

**목표**: 고용24 API에서 매일 자동으로 공고를 가져와 구조화된 테이블로 쌓는다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 1.1 | 고용24/공공데이터포털 API 키 발급, 스펙 조사, 샘플 응답 저장 | `docs/api-work24.md`, `tests/fixtures/` |
| 1.2 | Alembic 0001~0003 (raw, jobs, companies, skills, job_skills) | 마이그레이션 |
| 1.3 | Collector: 목록→상세 2단계 수집, 재시도, rate limit, content_hash | `src/jobfit/collectors/work24.py` |
| 1.4 | Celery 앱 + Redis 브로커 + Beat 스케줄 (매일 06:00 KST) | `src/jobfit/worker/` |
| 1.5 | Normalizer: Polars 변환 (경력/급여/학력/지역/마감 파싱) | `src/jobfit/processing/normalize.py` |
| 1.6 | 섹션 분리 (주요업무/자격요건/우대사항) | `processing/sections.py` |
| 1.7 | 스킬 사전 구축 (IT 200~300개 + 별칭) | `data/skills_seed.yaml` |
| 1.8 | 스킬 추출기 v1 (사전+정규식, 필수/우대 구분) | `src/jobfit/skills/extractor.py` |
| 1.9 | 파싱 단위 테스트 (엣지케이스 30개+) | `tests/test_normalize.py` |
| 1.10 | EDA 노트북: 수집 현황·직무/지역 분포·스킬 빈도 | `notebooks/01_eda.ipynb` |
| 1.11 | 데이터 품질 리포트 스크립트 | `scripts/quality_report.py` |

### DoD
- [ ] `jobs` 테이블에 10,000건+ 적재
- [ ] 필수 필드 누락률 < 5%, 급여/경력 파싱 성공률 > 80%
- [ ] 스킬 추출 정밀도 ≥ 0.85 (수동 검수 200건)
- [ ] Celery Beat이 매일 자동 수집 (중복 재처리 없음 확인)
- [ ] EDA 노트북에서 IT 직군 공고량이 충분한지 판단 완료

### 학습 포인트
멱등한 ETL 설계 / Raw 레이어를 남기는 이유 / Polars lazy API / 큐·워커·스케줄러 분리 / 데이터 품질 지표

---

## Phase 2 — ML 매칭 모델 (1.5주)

**목표**: 프로필-공고 적합도를 학습 모델로 산출하고, 실험을 재현 가능하게 관리한다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 2.1 | Alembic 0004~0005 (users, profiles, interactions, match_scores) | 마이그레이션 |
| 2.2 | 내 프로필 + 가상 프로필 20개 작성 (다양한 페르소나) | `data/profiles_seed.yaml` |
| 2.3 | 규칙 기반 베이스라인 스코어러 | `src/jobfit/matching/rule_scorer.py` |
| 2.4 | 라벨 생성: 규칙 pseudo-label + 수동 라벨 200쌍 | `data/labels.csv` |
| 2.5 | 피처 엔지니어링 (문서 03-3절 13개 피처) | `src/jobfit/matching/features.py` |
| 2.6 | scikit-learn 파이프라인 + 학습/검증 분할 (시간 기반) | `src/jobfit/matching/train.py` |
| 2.7 | XGBoost 랭킹 모델 (rank:pairwise) + 하이퍼파라미터 탐색 | 동일 |
| 2.8 | 평가: AUC, nDCG@10, MAP, 베이스라인 대비 개선폭 | `src/jobfit/matching/evaluate.py` |
| 2.9 | MLflow 컨테이너 + 실험 트래킹 + 모델 레지스트리 | compose 추가 |
| 2.10 | 스킬 갭 분석기 + `skill_market_stats` 일배치 | `src/jobfit/matching/skill_gap.py` |
| 2.11 | 배치 스코어링 Celery 태스크 | `worker/tasks/scoring.py` |

### DoD
- [ ] XGBoost가 규칙 베이스라인 대비 nDCG@10 개선 (수치로 증명)
- [ ] AUC ≥ 0.75, nDCG@10 ≥ 0.70
- [ ] MLflow UI에 5개 이상 실험 기록, 최적 모델이 Registry에 등록
- [ ] 학습 스크립트 재실행 시 동일 결과 (시드 고정)
- [ ] 내 프로필로 추천 Top-20을 눈으로 보고 납득 가능한지 확인

### 학습 포인트
데이터 누수 방지 / 랭킹 메트릭(nDCG) / 실험 추적의 필요성 / 피처 중요도 해석

---

## Phase 3 — 임베딩 & 벡터 검색 (1주)

**목표**: 자연어 문장으로 공고를 찾는 의미 검색을 구현한다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 3.1 | Alembic 0006 (`job_embeddings` + HNSW) | 마이그레이션 |
| 3.2 | 청킹 전략 구현 (섹션 + 슬라이딩 윈도우) | `src/jobfit/embedding/chunker.py` |
| 3.3 | e5-small 임베더 (passage/query 접두사, 배치, L2 정규화) | `src/jobfit/embedding/embedder.py` |
| 3.4 | 전체 공고 임베딩 배치 Celery 태스크 (진행률 로깅) | `worker/tasks/embedding.py` |
| 3.5 | 벡터 검색 (필터 + Top-K, pgvector 코사인 연산자) | `src/jobfit/embedding/search.py` |
| 3.6 | 하이브리드 검색 (tsvector 키워드 + 벡터, RRF 결합) | 동일 |
| 3.7 | 검색 평가셋 100쿼리 수동 작성 + Recall@10 측정 | `data/search_eval.yaml` |
| 3.8 | HNSW 파라미터/ef_search 튜닝 실험 | `notebooks/03_vector_tuning.ipynb` |

### DoD
- [ ] 전체 공고 임베딩 완료 (커버리지 ≥ 99%)
- [ ] Recall@10 ≥ 0.80, 검색 지연 p95 < 300ms (1만 건 기준)
- [ ] 하이브리드가 벡터 단독보다 우수함을 수치로 확인
- [ ] 자연어 쿼리 10개를 직접 던져 결과가 납득 가능

### 학습 포인트
임베딩 모델의 접두사 규약 / 청킹이 검색 품질에 미치는 영향 / HNSW 트레이드오프(속도↔재현율) / RRF

---

## Phase 4 — RAG & API (2주)

**목표**: 근거를 인용하는 커리어 상담 API를 만들고, **품질을 수치로 측정**한다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 4.1 | LLM 연동 설정 (Phase4는 API 사용, 인터페이스 추상화) | `src/jobfit/rag/llm.py` |
| 4.2 | LangChain LCEL 리트리버 (하이브리드 검색 래핑) | `src/jobfit/rag/retriever.py` |
| 4.3 | 쿼리 재작성 (멀티턴 문맥 반영) | `rag/query_rewrite.py` |
| 4.4 | 컨텍스트 조립 + 인용 태깅 + 토큰 예산 관리 | `rag/context.py` |
| 4.5 | 프롬프트 설계 (환각 억제, 인용 강제, 한국어) | `rag/prompts.py` |
| 4.6 | Pydantic 구조화 출력 (answer, citations, confidence) | `rag/schema.py` |
| 4.7 | 인용 검증기 (존재하지 않는 job_id 인용 차단) | `rag/verify.py` |
| 4.8 | FastAPI 전체 엔드포인트 구현 (문서 01-3절) | `src/jobfit/api/routers/` |
| 4.9 | SSE 스트리밍 응답 | `api/routers/chat.py` |
| 4.10 | 골든 데이터셋 60쌍 작성 | `data/rag_golden.yaml` |
| 4.11 | RAGAS 평가 파이프라인 + 리포트 | `src/jobfit/rag/eval.py` |
| 4.12 | 개선 루프: 청킹/Top-K/프롬프트 3회 이상 변주 후 비교 | `docs/rag-experiments.md` |
| 4.13 | 최소 데모 UI | `src/jobfit/api/templates/` |

### DoD
- [ ] RAGAS faithfulness ≥ 0.80, answer_relevancy ≥ 0.80, context_precision ≥ 0.75
- [ ] 모든 답변에 유효한 인용 포함 (인용 검증 100% 통과)
- [ ] 근거 없는 질문에 모른다고 답함 (반증 케이스 5개 통과)
- [ ] `/docs` OpenAPI에서 모든 엔드포인트 시도 가능
- [ ] 실험 3회 이상의 비교표가 문서에 기록

### 학습 포인트
RAG의 실패 지점(검색 실패 vs 생성 실패) 구분 / 평가 없는 RAG는 개선 불가 / LCEL 조합 / 스트리밍

---

## Phase 5 — 관측성 (0.5주)

**목표**: 서비스가 지금 건강한지, 어디가 느린지, LLM이 무엇을 했는지 눈으로 본다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 5.1 | `prometheus-fastapi-instrumentator` + 커스텀 메트릭 | `api/observability.py` |
| 5.2 | 도메인 메트릭: 수집 건수, 임베딩 지연, RAG 토큰/지연/인용수, 검색 히트율 | 동일 |
| 5.3 | Celery 메트릭 exporter | compose 추가 |
| 5.4 | Prometheus + Grafana 컨테이너 + 대시보드 3종 (API/파이프라인/RAG) | `infra/grafana/` |
| 5.5 | structlog JSON 로깅 + request_id 미들웨어 | `api/middleware.py` |
| 5.6 | LangSmith 트레이싱 연동 | `.env` + `rag/llm.py` |
| 5.7 | 알림 규칙 (에러율/지연/수집 실패) | `infra/prometheus/rules.yml` |

### DoD
- [ ] Grafana에서 API RPS/지연/에러율, 수집 성공률, RAG 지연·비용이 보임
- [ ] LangSmith에서 RAG 호출 트레이스 확인
- [ ] 로그에서 `request_id`로 한 요청의 전 구간 추적 가능

### 학습 포인트
RED 메트릭(Rate/Error/Duration) / 히스토그램과 p95 / LLM 관측성의 특수성(토큰·비용·품질)

---

## Phase 6 — 에이전트 & 보안 (1.5주)

**목표**: 스스로 여러 단계를 수행하는 커리어 플래너를 만들고, 서비스를 인증으로 보호한다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 6.1 | JWT 인증 (signup/login/refresh), bcrypt 해시 | `src/jobfit/api/auth/` |
| 6.2 | 의존성 주입 기반 인가 (`get_current_user`) | 동일 |
| 6.3 | OAuth2 소셜 로그인 (Google) | `auth/oauth.py` |
| 6.4 | Rate limiting (Redis 기반) | `api/middleware.py` |
| 6.5 | MCP 서버: `search_jobs`, `get_skill_stats`, `compute_skill_gap` | `src/jobfit/mcp_server/` |
| 6.6 | LangGraph StateGraph 설계 (문서 02-3.7절) | `src/jobfit/agents/career_planner.py` |
| 6.7 | 조건부 엣지 + 루프 제한 + 체크포인터(Postgres) | 동일 |
| 6.8 | 에이전트 비동기 실행 (Celery) + 상태 조회 API | `api/routers/agent.py` |
| 6.9 | 에이전트 평가: 10개 프로필로 로드맵 생성 후 품질 검토 | `docs/agent-eval.md` |

### DoD
- [ ] 인증 없이 보호 엔드포인트 접근 시 401
- [ ] 토큰 만료/갱신 동작 확인
- [ ] 에이전트가 내 프로필로 6개월 로드맵 생성 (근거 공고 포함)
- [ ] LangSmith에서 그래프 노드별 실행 추적 가능
- [ ] 무한 루프 방지 확인 (max_iterations)

### 학습 포인트
JWT의 상태 비저장 / 그래프 기반 에이전트 vs 단순 체인 / MCP로 도구를 표준화하는 이유 / 에이전트 평가의 어려움

---

## Phase 7 — 오케스트레이션 & 배포 (1.5주)

**목표**: 사람 손 없이 매일 돌고, 인터넷에서 접속되는 시스템으로 만든다.

### 작업
| # | 작업 | 산출물 |
|---|---|---|
| 7.1 | Airflow 도입 (compose), Celery Beat → Airflow 이관 | `airflow/docker-compose.yml` |
| 7.2 | DAG: `daily_ingest` (수집→정규화→스킬→임베딩→통계) | `airflow/dags/daily_ingest.py` |
| 7.3 | DAG: `weekly_retrain` (라벨생성→학습→평가→MLflow등록→조건부 배포) | `airflow/dags/weekly_retrain.py` |
| 7.4 | 센서/브랜치/백필 실습 | 동일 |
| 7.5 | multi-arch 이미지 빌드 (buildx, amd64+arm64) → GHCR | `.github/workflows/release.yml` |
| 7.6 | Oracle ARM 서버에 k3s 설치 | 서버 |
| 7.7 | k8s 매니페스트 (Deployment/Service/Ingress/Secret/PVC) | `infra/k3s/` |
| 7.8 | Postgres StatefulSet + 백업 CronJob | 동일 |
| 7.9 | Ingress + TLS 인증서 자동 발급 (cert-manager) | 동일 |
| 7.10 | Ollama 배포 + 소형 모델 서빙, RAG LLM 교체 실험 | `infra/k3s/ollama.yaml` |
| 7.11 | (선택) PEFT/LoRA로 스킬 추출 또는 직무 분류 소형 모델 파인튜닝 | `notebooks/07_peft.ipynb` |
| 7.12 | CD 워크플로 (main 머지 → 이미지 푸시 → 롤링 업데이트) | `.github/workflows/cd.yml` |
| 7.13 | 운영 문서: 장애 대응, 백업/복구, 롤백 절차 | `docs/runbook.md` |

### DoD
- [ ] Airflow UI에서 일일 DAG가 3일 연속 성공
- [ ] 공개 도메인(HTTPS)으로 API 접속 가능
- [ ] `git push` → 자동 배포 → 무중단 롤링 업데이트 확인
- [ ] Ollama 로컬 LLM으로 RAG 동작 (품질/지연 비교표 작성)
- [ ] DB 백업 파일로 복구 리허설 1회 완료

### 학습 포인트
스케줄러의 멱등성·백필 / 멀티아키텍처 빌드 / k8s 리소스 모델 / 자체 LLM 서빙의 현실적 트레이드오프

---

## Phase 이후 (선택)

- 협업 필터링 추가 (상호작용 데이터 축적 후)
- A/B 테스트 프레임워크
- 공고 마감 예측 / 급여 예측 회귀 모델
- 포트폴리오용 기술 블로그 시리즈 작성 (Phase별 1편)
