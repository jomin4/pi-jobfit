# 01. 요구사항 명세

> 이전 ← [00-charter.md](00-charter.md) · 다음 → [02-architecture.md](02-architecture.md)

---

## 1. 기능 요구사항 (FR)

### FR-1. 데이터 수집 (Phase 1)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-1.1 | 고용24(워크넷) 채용정보 OpenAPI에서 공고 목록/상세를 조회한다 | P0 |
| FR-1.2 | 수집 원문(JSON/XML)을 가공 없이 `raw_job_postings`에 보존한다 | P0 |
| FR-1.3 | `content_hash`로 중복/변경 없는 공고는 재처리하지 않는다 | P0 |
| FR-1.4 | 수집은 Celery 태스크로 비동기 실행되며 재시도(지수 백오프)를 지원한다 | P0 |
| FR-1.5 | API 호출 속도 제한(rate limit)을 준수한다 | P0 |
| FR-1.6 | 수집 실행 이력(건수/성공/실패/소요시간)을 `ingestion_runs`에 기록한다 | P1 |

### FR-2. 정규화 & 스킬 추출 (Phase 1)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-2.1 | 원문을 `jobs` 테이블 스키마(직무명, 경력, 학력, 급여, 지역, 마감일 등)로 정규화한다 | P0 |
| FR-2.2 | 급여 문자열("연 3,600만원 이상")을 정수 범위로 파싱한다 | P0 |
| FR-2.3 | 경력 조건("경력 3년 이상", "신입/경력")을 `exp_min`/`exp_max`로 파싱한다 | P0 |
| FR-2.4 | 스킬 사전(별칭 포함)을 기반으로 공고 본문에서 스킬을 추출한다 | P0 |
| FR-2.5 | 스킬이 "필수/우대" 중 어디 문단에 등장했는지 구분한다 | P1 |
| FR-2.6 | 정규화 결과의 품질 지표(누락률, 파싱 실패율)를 산출한다 | P1 |

### FR-3. 사용자 & 프로필 (Phase 2, 6)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-3.1 | 회원가입/로그인 (이메일+비밀번호, JWT 발급) | P0 (Phase 6) |
| FR-3.2 | 프로필 등록: 경력연차, 보유 스킬(+숙련도), 희망 직무/지역/연봉, 학력 | P0 |
| FR-3.3 | 이력서 텍스트를 붙여넣으면 스킬을 자동 추출해 프로필을 채운다 | P1 |
| FR-3.4 | 공고에 대한 상호작용(조회/저장/지원/숨김)을 기록한다 | P0 |

### FR-4. 매칭 & 추천 (Phase 2)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-4.1 | 프로필-공고 쌍에 대해 0~100 적합도 점수를 산출한다 | P0 |
| FR-4.2 | 점수의 근거(스킬 일치율, 경력 적합, 지역, 급여)를 함께 반환한다 | P0 |
| FR-4.3 | 규칙 기반 베이스라인 → XGBoost 모델 순으로 고도화한다 | P0 |
| FR-4.4 | 모델 학습/평가 실험은 MLflow에 기록되고 재현 가능해야 한다 | P0 |
| FR-4.5 | 스킬 갭: 목표 직무의 요구 스킬 빈도 대비 미보유 스킬 Top-N을 산출한다 | P0 |

### FR-5. 의미 검색 (Phase 3)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-5.1 | 공고 텍스트를 청크 분할 후 `multilingual-e5-small`로 임베딩한다 | P0 |
| FR-5.2 | pgvector HNSW 인덱스로 코사인 유사도 Top-K 검색을 제공한다 | P0 |
| FR-5.3 | 키워드(BM25/tsvector) + 벡터 하이브리드 검색을 지원한다 | P1 |
| FR-5.4 | 필터(지역/경력/직무)와 벡터 검색을 함께 적용한다 | P0 |

### FR-6. RAG 상담 (Phase 4)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-6.1 | 자연어 질문에 대해 관련 공고를 검색하고 근거를 인용해 답변한다 | P0 |
| FR-6.2 | 답변에 인용된 공고 ID/제목/URL을 반드시 포함한다 | P0 |
| FR-6.3 | 근거가 부족하면 "모른다"고 답한다 (환각 억제) | P0 |
| FR-6.4 | RAGAS로 faithfulness/answer_relevancy/context_precision을 정기 평가한다 | P0 |
| FR-6.5 | 대화 세션/메시지를 저장하고 멀티턴 문맥을 유지한다 | P1 |

### FR-7. 에이전트 (Phase 6)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-7.1 | LangGraph로 `프로필분석 → 시장조사 → 갭분석 → 로드맵생성` 그래프를 구성한다 | P0 |
| FR-7.2 | 에이전트가 내부 도구(공고검색/통계조회/스킬갭)를 MCP 서버로 호출한다 | P0 |
| FR-7.3 | 각 노드의 중간 산출물을 상태로 보존하고 추적 가능하게 한다 | P0 |

### FR-8. 운영 (Phase 5, 7)
| ID | 요구사항 | 우선순위 |
|---|---|---|
| FR-8.1 | Prometheus 메트릭(`/metrics`)을 노출하고 Grafana 대시보드를 제공한다 | P0 |
| FR-8.2 | LLM 호출은 LangSmith로 트레이싱한다 | P0 |
| FR-8.3 | Airflow DAG로 일일 수집→정규화→임베딩→모델 재학습 파이프라인을 스케줄링한다 | P0 |
| FR-8.4 | GitHub Actions에서 lint/test/build/push가 자동 실행된다 | P0 (Phase 0) |

---

## 2. 비기능 요구사항 (NFR)

| ID | 항목 | 요구사항 |
|---|---|---|
| NFR-1 | 성능 | 검색 API p95 < 1.5s, 적합도 계산 100건 < 500ms |
| NFR-2 | 확장성 | 공고 50만 건까지 스키마/인덱스 변경 없이 동작 |
| NFR-3 | 재현성 | `docker compose up` 한 번으로 전체 로컬 환경 기동 |
| NFR-4 | 이식성 | x86_64(로컬)와 ARM64(Oracle) 모두에서 동일 이미지 빌드 |
| NFR-5 | 보안 | 비밀번호 bcrypt 해시, JWT 만료 30분 + refresh, 시크릿은 `.env`/GitHub Secrets |
| NFR-6 | 관측성 | 모든 요청에 `request_id` 부여, 구조화 로그(JSON) 출력 |
| NFR-7 | 데이터 | 원문 보존(immutable raw layer), 재처리로 하위 레이어 복구 가능 |
| NFR-8 | 비용 | 월 고정비 0원 (Oracle Always Free + 무료 티어 서비스) |
| NFR-9 | 품질 | 핵심 로직 테스트 커버리지 ≥ 60%, CI에서 ruff+mypy 통과 |

---

## 3. API 초안 (Phase 4에서 확정)

```
POST   /api/v1/auth/signup            회원가입
POST   /api/v1/auth/login             로그인 → access/refresh token
GET    /api/v1/me/profile             내 프로필 조회
PUT    /api/v1/me/profile             프로필 수정
POST   /api/v1/me/profile/parse       이력서 텍스트 → 스킬 자동 추출

GET    /api/v1/jobs                   공고 목록 (필터 + 페이징)
GET    /api/v1/jobs/{job_id}          공고 상세
POST   /api/v1/jobs/search            의미 검색 {query, filters, top_k}

POST   /api/v1/match/recommend        내 프로필 기준 추천 공고 + 점수 + 근거
POST   /api/v1/match/explain          특정 공고에 대한 적합도 상세 분석
GET    /api/v1/match/skill-gap        목표 직무 대비 스킬 갭

POST   /api/v1/chat/sessions          대화 세션 생성
POST   /api/v1/chat/sessions/{id}/messages   RAG 질의응답 (SSE 스트리밍)

POST   /api/v1/agent/career-plan      에이전트 커리어 로드맵 생성 (비동기 job)
GET    /api/v1/agent/jobs/{task_id}   에이전트 작업 상태/결과

GET    /metrics                       Prometheus
GET    /health                        헬스체크
```

---

## 4. 데이터 품질 규칙 (Data Contract)

| 필드 | 규칙 | 위반 시 |
|---|---|---|
| `jobs.source_id` | NOT NULL, `(source, source_id)` UNIQUE | 적재 거부 |
| `jobs.title` | NOT NULL, 길이 1~300 | 적재 거부 |
| `jobs.exp_min` | 0 ≤ exp_min ≤ exp_max ≤ 40 | NULL 처리 + 경고 로그 |
| `jobs.salary_min` | 0 또는 1,000,000 이상(원/년) | NULL 처리 |
| `jobs.deadline` | 파싱 실패 시 NULL 허용 (상시채용 존재) | NULL |
| `job_skills.confidence` | 0.0 ~ 1.0 | 적재 거부 |
| 임베딩 | 차원 = 384, L2 정규화 완료 | 적재 거부 |
