# 06. 기술 스택 가이드 (왜 쓰는가)

> 이전 ← [05-conventions.md](05-conventions.md)
> 각 기술을 **이 프로젝트에서 무엇에 쓰는지**, **왜 골랐는지**, **대안은 무엇인지** 한눈에.
> 해당 Phase 시작 전에 이 항목만 다시 읽으면 됩니다.

---

## Phase 0 — 기반

### Docker / Docker Compose
- **무엇**: 애플리케이션과 의존성을 이미지로 묶어 어디서나 동일하게 실행
- **여기서**: Postgres, Redis, API, Worker, MLflow, Grafana를 한 번에 기동
- **핵심 개념**: 이미지 vs 컨테이너 / 볼륨(데이터 영속) / 네트워크(서비스명으로 통신) / 레이어 캐시
- **자주 하는 실수**: 컨테이너 안에서 `localhost`는 컨테이너 자신. DB 주소는 `postgres`(서비스명)

### GitHub Actions
- **무엇**: push/PR 시 자동으로 검사·빌드·배포하는 CI/CD
- **여기서**: lint → typecheck → test → 멀티아키 이미지 빌드 → GHCR 푸시 → 배포
- **핵심 개념**: workflow / job / step / matrix / secrets / cache
- **왜**: "내 컴퓨터에서는 되는데"를 원천 차단. 배포 자동화의 출발점

### Oracle Cloud (Ampere A1, ARM64)
- **무엇**: Always Free로 ARM 4 OCPU / 24GB RAM을 영구 무료 제공
- **여기서**: 최종 운영 서버 (k3s 단일 노드)
- **주의**: ARM64라서 일부 파이썬 wheel이 없다 → 멀티아키 빌드 필요. Phase 0에서 미리 검증

---

## Phase 1 — 데이터

### Python / SQL
- **여기서**: 전 구간의 언어. SQL은 집계·윈도우 함수·CTE를 직접 작성 (ORM에만 의존하지 않음)

### Pandas / Polars / NumPy
- **Polars**: Rust 기반, lazy 실행 + 멀티스레드. **대용량 배치 변환**에 사용
- **Pandas**: 생태계가 넓고 시각화/노트북에 편함. **EDA·분석**에 사용
- **NumPy**: 벡터 연산, 임베딩 배열 처리, 피처 계산
- **왜 둘 다**: 현업에서도 파이프라인은 Polars/Spark, 분석은 Pandas로 나뉘는 경우가 흔함
- **Polars 핵심**: `pl.scan_*` → `.filter().with_columns()` → `.collect()` (지연 실행으로 최적화)

### PostgreSQL
- **여기서**: 유일한 저장소. 관계형 + JSONB(원문) + tsvector(전문검색) + vector(임베딩)
- **핵심 개념**: 인덱스 종류(B-tree/GIN/HNSW) / EXPLAIN ANALYZE / 트랜잭션 격리 / UPSERT
- **왜**: 개인 프로젝트 규모에서 저장소를 쪼개면 동기화 비용만 늘어남

### pgvector
- **무엇**: Postgres에 벡터 타입과 유사도 인덱스를 추가하는 확장
- **여기서**: 공고 임베딩 저장 + 코사인 유사도 Top-K 검색
- **핵심 개념**: 연산자 `<=>`(코사인) `<->`(L2) / HNSW vs IVFFlat / `ef_search` 튜닝
- **대안**: Qdrant, Pinecone, Weaviate — 100만 벡터 이상이면 고려

### Redis
- **여기서**: (1) Celery 메시지 브로커 (2) 검색 결과·임베딩 캐시 (3) rate limit 카운터
- **핵심 개념**: TTL / 자료구조(String, Hash, Sorted Set) / 원자적 연산

### Celery
- **무엇**: 파이썬 분산 작업 큐
- **여기서**: 수집·정규화·임베딩·스코어링 등 오래 걸리는 작업을 API와 분리
- **핵심 개념**: broker vs backend / 워커 동시성 / `acks_late` / 재시도 / Beat(주기 실행) / 멱등성
- **주의**: 태스크는 반드시 재실행 가능해야 함 (중간에 죽어도 안전)

---

## Phase 2 — 머신러닝

### Scikit-learn
- **여기서**: 전처리 파이프라인, 교차검증, 베이스라인 모델, 평가 메트릭
- **핵심 개념**: `Pipeline`(전처리+모델을 한 객체로) / `ColumnTransformer` / 시간 기반 분할

### XGBoost
- **무엇**: 그래디언트 부스팅 트리. 정형 데이터에서 딥러닝보다 강한 경우가 많음
- **여기서**: 프로필-공고 적합도 랭킹 모델 (`rank:pairwise`)
- **핵심 개념**: 랭킹 목적함수 / `feature_importance`·SHAP / 조기 종료 / 과적합 제어
- **평가 메트릭**: AUC(이진 적합 여부), **nDCG@K**(순위 품질 — 추천에서 가장 중요)

### MLflow
- **무엇**: 실험 추적 + 모델 레지스트리
- **여기서**: 하이퍼파라미터·메트릭·아티팩트를 기록하고 실험을 비교, 최고 모델을 등록
- **핵심 개념**: run / experiment / artifact / Model Registry(Staging→Production)
- **왜**: "지난주에 0.72 나온 그 설정이 뭐였지?"를 없앤다

---

## Phase 3 — 임베딩

### multilingual-e5-small
- **무엇**: 다국어 문장 임베딩 모델. 384차원, 약 118M 파라미터 → **CPU로 충분**
- **여기서**: 공고 청크와 검색 쿼리를 같은 벡터 공간에 매핑
- **반드시 지킬 것**: 문서에는 `passage: ` 쿼리에는 `query: ` 접두사. 안 붙이면 성능이 크게 떨어짐
- **후처리**: L2 정규화 → 내적 = 코사인 유사도
- **대안**: `bge-m3`(고성능·무거움), `KoSimCSE`(한국어 특화), OpenAI embeddings(유료·외부 의존)

---

## Phase 4 — RAG & API

### LangChain
- **무엇**: LLM 애플리케이션 조립 프레임워크
- **여기서**: 리트리버 → 프롬프트 → LLM → 파서 체인(LCEL)을 구성
- **핵심 개념**: LCEL 파이프 연산자 / Runnable / 스트리밍 / 구조화 출력
- **주의**: 추상화가 두꺼워 디버깅이 어려울 수 있음 → 핵심 로직은 직접 짜고 조립만 맡긴다

### FastAPI / Pydantic
- **FastAPI**: async 기반 웹 프레임워크. 타입 힌트에서 검증·문서를 자동 생성
- **Pydantic**: 데이터 검증/직렬화. 설정(`pydantic-settings`), API 스키마, LLM 구조화 출력에 전부 사용
- **핵심 개념**: 의존성 주입(`Depends`) / `response_model` / 백그라운드 태스크 / SSE 스트리밍

### RAGAS
- **무엇**: RAG 품질을 LLM 기반으로 정량 평가하는 프레임워크
- **주요 지표**
  - `faithfulness`: 답변이 검색된 문맥에 충실한가 (**환각 측정**)
  - `answer_relevancy`: 답변이 질문에 적절한가
  - `context_precision`: 검색된 문맥 중 실제로 쓸모 있는 비율
  - `context_recall`: 정답에 필요한 문맥을 다 가져왔는가
- **왜**: 검색 실패인지 생성 실패인지 구분해야 개선 방향이 정해짐

---

## Phase 5 — 관측성

### Prometheus / Grafana
- **Prometheus**: 시계열 메트릭 수집(pull 방식). `/metrics`를 주기적으로 긁어감
- **Grafana**: 그 메트릭을 대시보드로 시각화
- **핵심 개념**: Counter/Gauge/Histogram / 라벨 / PromQL / `histogram_quantile`로 p95 계산
- **RED 방법론**: Rate(요청량) · Errors(에러율) · Duration(지연) — 서비스 건강의 3대 지표

### LangSmith
- **무엇**: LLM 호출 전용 트레이싱. 프롬프트/응답/토큰/지연/체인 구조를 그대로 기록
- **왜**: 일반 APM으로는 "LLM이 왜 그렇게 답했는지"를 볼 수 없다

---

## Phase 6 — 에이전트 & 보안

### LangGraph
- **무엇**: 상태를 가진 **그래프**로 에이전트를 표현 (노드=단계, 엣지=전이)
- **왜 체인이 아니라 그래프**: 조건 분기, 반복(자기 비평 후 재생성), 사람 개입 지점이 필요하기 때문
- **핵심 개념**: `StateGraph` / 조건부 엣지 / 체크포인터(중단·재개) / 재귀 제한

### MCP (Model Context Protocol)
- **무엇**: LLM에게 도구/데이터를 제공하는 **표준 프로토콜**
- **여기서**: 공고 검색·스킬 통계·갭 계산을 MCP 서버로 노출 → LangGraph 에이전트와 다른 클라이언트가 동일 도구를 사용
- **왜**: 도구를 특정 프레임워크에 묶지 않는다

### JWT / OAuth2
- **JWT**: 서명된 토큰에 사용자 정보를 담아 서버 세션 없이 인증
- **OAuth2**: 구글 등 외부 제공자에 인증을 위임
- **핵심 개념**: access(짧게) + refresh(길게) / 서명 검증 / 만료 / 안전한 저장
- **주의**: JWT는 서버가 즉시 무효화하기 어렵다 → 만료를 짧게, 필요 시 블랙리스트

---

## Phase 7 — 운영

### Airflow
- **무엇**: DAG(방향성 비순환 그래프)로 배치 작업의 의존성과 스케줄을 관리
- **여기서**: 일일 수집 파이프라인, 주간 모델 재학습
- **핵심 개념**: DAG/Task/Operator / execution_date와 **백필** / 센서 / 재시도 / XCom
- **Celery와의 차이**: Celery는 "작업 큐", Airflow는 "작업 흐름과 일정 관리". 서로 대체재가 아님

### k3s
- **무엇**: 경량 Kubernetes 배포판. ARM 단일 노드에서도 잘 돈다
- **핵심 개념**: Pod/Deployment/Service/Ingress / ConfigMap·Secret / PVC / 롤링 업데이트·롤백 / 리소스 requests·limits

### Ollama / vLLM
- **Ollama**: 로컬에서 오픈 LLM을 간단히 서빙 (CPU/소형 모델 가능)
- **vLLM**: GPU 환경에서 고성능 추론 (PagedAttention, 연속 배칭)
- **여기서**: Phase 4는 API LLM으로 품질 기준선을 잡고, Phase 7에서 자체 서빙으로 교체 후 **품질·지연·비용 비교표** 작성

### PyTorch / Hugging Face / PEFT
- **여기서**: 임베딩 모델 로딩(transformers/sentence-transformers), 선택 과제로 LoRA 파인튜닝
- **PEFT/LoRA**: 전체 가중치 대신 작은 어댑터만 학습 → 적은 자원으로 도메인 특화
- **현실**: CPU만으로는 파인튜닝이 사실상 어려움 → Colab 또는 단기 GPU 대여 활용

---

## 자주 헷갈리는 개념 정리

| 헷갈림 | 정리 |
|---|---|
| Celery vs Airflow | Celery=작업 실행 큐 / Airflow=스케줄·의존성 관리. Airflow가 Celery를 실행기로 쓰기도 함 |
| 임베딩 vs 파인튜닝 | 임베딩=텍스트를 벡터로 (검색용) / 파인튜닝=모델 가중치를 바꿈 (행동 변경) |
| RAG vs 파인튜닝 | 지식 주입은 RAG, 형식·스타일·도메인 어투는 파인튜닝 |
| 벡터검색 vs 키워드검색 | 벡터=의미 유사("배치처리"↔"대용량 데이터 처리") / 키워드=정확 일치("Kubernetes"). **둘을 합친 하이브리드가 보통 최선** |
| AUC vs nDCG | AUC=분류를 잘하나 / nDCG=순서를 잘 매기나. 추천은 nDCG가 본질 |
| Prometheus vs LangSmith | 시스템 지표 vs LLM 내부 동작. 둘 다 필요 |
