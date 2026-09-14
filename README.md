# JobFit — 채용공고 기반 커리어 매칭

공공 채용 데이터를 수집·구조화하고, 구직자 프로필과의 **적합도를 점수로 산출**하며,
**부족한 스킬과 학습 경로까지 제안**하는 AI 커리어 매칭 서비스.

> 개인 학습 프로젝트. 기획 → 데이터 파이프라인 → ML → 임베딩 → RAG → 관측 → 에이전트 → 배포까지
> AI 엔지니어링 전 과정을 직접 구현하는 것이 목적입니다.

---

## 문서

| 문서 | 내용 |
|---|---|
| [00. 기획서](docs/00-charter.md) | 문제 정의, 페르소나, 유스케이스, 성공 지표 |
| [01. 요구사항](docs/01-requirements.md) | 기능/비기능 요구사항, API 초안, 데이터 계약 |
| [02. 아키텍처](docs/02-architecture.md) | 시스템 구성, 컴포넌트 설계, 배포 토폴로지, 기술 선택 근거 |
| [03. 데이터 모델](docs/03-data-model.md) | ERD, 테이블 스키마, 피처 정의, 마이그레이션 순서 |
| [04. 로드맵](docs/04-roadmap.md) | **Phase 0~7 작업 목록과 완료 기준(DoD)** |
| [05. 개발 규약](docs/05-conventions.md) | 디렉터리 구조, 코딩/Git/테스트 규약, 환경변수 |
| [06. 기술 가이드](docs/06-glossary.md) | 각 기술을 왜 쓰는가 / 핵심 개념 / 대안 |
| [트러블슈팅](docs/troubleshooting/README.md) | 실제로 막혔던 문제와 진단 과정 기록 |

---

## 기술 스택

| 영역 | 스택 | Phase |
|---|---|---|
| Language | Python 3.12, SQL | 1 |
| Data Processing | Polars, Pandas, NumPy | 1 |
| Async / Queue | Celery, Redis | 1 |
| Database | PostgreSQL 16, pgvector, Redis | 1 |
| ML | scikit-learn, XGBoost | 2 |
| Experiment | MLflow | 2 |
| Embedding | multilingual-e5-small | 3 |
| RAG | LangChain | 4 |
| API | FastAPI, Pydantic | 4 |
| Evaluation | RAGAS | 4 |
| Observability | LangSmith, Prometheus, Grafana | 5 |
| Agent | LangGraph, MCP | 6 |
| Security | JWT, OAuth2 | 6 |
| Orchestration | Airflow | 7 |
| Container | Docker, Docker Compose, k3s | 0, 7 |
| CI/CD | GitHub Actions | 0 |
| Cloud | Oracle Cloud (Ampere A1, ARM64) | 0 |
| LLM Serving | Ollama | 7 |
| Deep Learning | PyTorch, Hugging Face, PEFT | 7 |

---

## 진행 현황

- [x] **Phase 0** 기반 환경 · CI *(클라우드 배포는 Phase 7로 연기)*
- [ ] **Phase 1** 데이터 파이프라인
- [ ] **Phase 2** ML 매칭 모델
- [ ] **Phase 3** 임베딩 · 벡터 검색
- [ ] **Phase 4** RAG · API
- [ ] **Phase 5** 관측성
- [ ] **Phase 6** 에이전트 · 보안
- [ ] **Phase 7** 오케스트레이션 · 배포

---

## 빠른 시작 (Phase 0 완료 후)

```bash
cp .env.example .env
docker compose up -d
alembic upgrade head
curl http://localhost:8000/health
```
