# 고용24(워크넷) 채용정보 OpenAPI 명세

> 작업 1.1 산출물 · 최종 갱신 2026-09-14
> 출처: https://www.work24.go.kr/cm/e/a/0110/selectOpenApiSvcInfo.do?fullApiSvcId=000000000000000000000000000000
> 이 문서가 `collectors/work24.py` 와 `03-data-model.md` 매핑의 기준이다.

---

## 0. 🚨 블로커 — 개인회원은 이 API를 쓸 수 없다 (2026-09-15 확정)

채용정보 API 활용신청이 승인된 인증키로도 다음 응답이 온다.

```xml
<GO24><error>개인회원은 사용할 수 없는 OPEN-API입니다.</error></GO24>
```

### 확인 경로 (에러 메시지의 변화가 곧 진단 로그)
| 단계 | 응답 | 해석 |
|---|---|---|
| 1 | `authKey는 필수 입니다` | 파라미터 누락 |
| 2 | `신청하신 OpenApi 서비스가 존재하지 않습니다` | 키는 유효, 해당 API 미신청 |
| 3 | **`개인회원은 사용할 수 없는 OPEN-API입니다`** | 신청 승인됨, **계정 등급 미달** |

에러가 단계마다 바뀌었기 때문에 "키 문제 → 권한 문제 → 등급 문제"로 원인을 좁힐 수 있었다.

### 우회로 없음
- 레거시 워크넷 OpenAPI(`openapi.work.go.kr/opiMain.do`)는 **서비스 종료**.
  > "워크넷 OPEN-API서비스가 고용24 OPEN-API로 통합되었습니다"
- 공공데이터포털(data.go.kr 3038225)은 **LINK 유형** — 포털이 중계하지 않고
  고용24 서버를 직접 호출하므로 동일한 제한을 받는다.

→ **기업회원(사업자등록번호 보유) 전환** 외에는 이 API를 쓸 방법이 없다.
→ 데이터 소스 대안은 [decisions/ADR-001-data-source.md](decisions/ADR-001-data-source.md) 참조.

**단, 아래 명세 조사는 그대로 유효하다.** 기업회원 전환 시 즉시 사용 가능하고,
다른 소스를 쓰더라도 "채용공고 API는 이런 모양"이라는 설계 기준으로 쓸 수 있다.

---

## 1. 기본 정보

| 항목 | 내용 |
|---|---|
| API 명 | 한국고용정보원 워크넷 채용정보 (채용목록 / 채용상세) |
| 포맷 | **XML (UTF-8)**, HTTP GET |
| 인증 | `authKey` (UUID 36자) — 고용24 회원가입 + **API별 활용신청** |
| 비용 | 무료 |
| 라이선스 | **공공저작물 제4유형**: 출처표시 + **상업적 이용금지** + 변경금지 |

### ⚠️ 엔드포인트가 두 세대 공존한다
| 세대 | URL | 비고 |
|---|---|---|
| **고용24 (현행)** | `https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210*.do` | **우리가 쓸 것** |
| 레거시 워크넷 | `https://openapi.work.go.kr/opi/opi/opia/wantedApi.do` | 아직 응답하나 **인증키 레지스트리가 별개** |

고용24 키를 레거시 URL에 넣으면 `[002] 유효하지 않은 인증키` 가 나온다.
**키가 틀린 게 아니라 엔드포인트가 틀린 것.** 이 프로젝트에서 실제로 30분을 썼다.

### 에러 메시지로 원인 구분하기 (실측)
| 응답 | 의미 |
|---|---|
| `<GO24><error>authKey는 필수 입니다.</error>` | 파라미터 누락 |
| `<GO24><error>신청하신 OpenApi 서비스가 존재하지 않습니다</error>` | **키는 인식됨.** 해당 API 활용신청이 없거나 미승인 |
| (레거시) `[002] 유효하지 않은 인증키` | 이 서버가 모르는 키 |

---

## 2. 엔드포인트

### 2.1 채용정보 목록 — `210L01`
```
https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
  ?authKey=[인증키]&callTp=L&returnType=XML&startPage=1&display=10
```

### 2.2 채용정보 상세 — `210D01`
```
https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210D01.do
  ?authKey=[인증키]&callTp=D&returnType=XML&wantedAuthNo=[구인인증번호]&infoSvc=VALIDATION
```
> 서비스 코드가 경로에 박혀 있다. `210L02` 는 **404** — 임의 추측 불가.

---

## 3. 요청 파라미터

### 3.1 공통 필수
| 파라미터 | 값 | 비고 |
|---|---|---|
| `authKey` | UUID | **대소문자 구분**. `authkey` 는 누락 처리 |
| `callTp` | `L` 목록 / `D` 상세 | |
| `returnType` | `XML` | 생략 시 에러 |

### 3.2 목록 전용 필수
| 파라미터 | 기본 | **최대** | 비고 |
|---|---|---|---|
| `startPage` | 1 | **1000** | |
| `display` | 10 | **100** | |

> **수집 상한**: 한 검색조건당 `100 × 1000 = 100,000건`.
> 이를 넘으면 조건(직종·지역·기간)을 쪼개 수집해야 한다.

### 3.3 상세 전용 필수
| 파라미터 | 값 |
|---|---|
| `wantedAuthNo` | 구인인증번호 (목록 응답에서 획득) |
| `infoSvc` | `VALIDATION` (워크넷 인증) |

### 3.4 우리가 쓸 선택 파라미터
| 파라미터 | 용도 | 값 |
|---|---|---|
| `occupation` | **IT 직종 한정** | 직종코드 (다중 가능, `\|` 구분). 과다 입력 시 제한 |
| `region` | 지역 필터 | 근무지역코드 (다중 가능) |
| `regDate` | **증분 수집** | `D-0` 오늘 / `D-3` / `W-1` / `W-2` / `M-1` |
| `minWantedAuthDt` / `maxWantedAuthDt` | **백필** | 구인인증일자 범위 |
| `sortOrderBy` | 페이징 안정화 | `DESC`(기본) / `ASC` |
| `empTpGb` | 채용구분 | `1` 상용직(기본) / `2` 일용직 |

### 3.5 기타 선택 파라미터 (참고)
`salTp`(임금형태 D/H/M/Y) · `minPay`/`maxPay` · `education`(00~07) ·
`career`(N 신입/E 경력/Z 무관) + `minCareerM`/`maxCareerM`(**개월 단위**) ·
`empTp`(고용형태) · `coTp`(기업형태) · `workerCnt`(사원수) · `welfare`(근무편의) ·
`keyword` · `major`(전공) · `foreignLanguage` · `certificate` · `workHrCd`(근무시간) ·
`subway`(역세권) · `busino`(사업자번호) · `dtlSmlgntYn`(강소기업) · `workStudyJoinYn`(일학습병행) ·
`untilEmpWantedYn`(채용시까지) · `scrapInfoYn` · `pref`(우대조건) · `holidayTp`(근무형태) ·
`termContractMmcnt`(근무기간) · `comPreferential`(컴퓨터활용) · `pfPreferential`(일반우대)

---

## 4. 응답 구조

### 4.1 목록 `<wantedRoot>`
```
<wantedRoot>
  <total>          총건수
  <startPage>      시작위치
  <display>        출력건수
  <wanted>                        ← 반복
    <wantedAuthNo>   구인인증번호   ★ 상세 조회 키 = jobs.source_id
    <company>        회사명
    <busino>         사업자등록번호  ★ 회사 식별 키
    <indTpNm>        업종
    <title>          채용제목
    <salTpNm> <sal> <minSal> <maxSal>    임금형태 / 급여 / 최소 / 최대
    <region>         근무지역
    <holidayTpNm>    근무형태
    <minEdubg> <maxEdubg>                최소·최대 학력
    <career>         경력
    <regDt> <closeDt>                    등록일 / 마감일
    <infoSvc>        정보제공처 (VALIDATION)
    <wantedInfoUrl> <wantedMobileInfoUrl>
    <zipCd> <strtnmCd> <basicAddr> <detailAddr>   주소
    <empTpCd>        고용형태코드
    <jobsCd>         직종코드
    <smodifyDtm>     최종수정일   ★ 변경 감지에 활용
```

### 4.2 상세 `<wantedDtl>` — **본문 텍스트는 여기 있다**
```
<wantedDtl>
  <wantedAuthNo>
  <corpInfo>                               ← companies 테이블 강화
    <corpNm> <reperNm> <totPsncnt> <capitalAmt> <yrSalesAmt>
    <indTpCdNm> <busiCont> <corpAddr> <homePg> <busiSize>
  </corpInfo>
  <wantedInfo>
    <jobsNm>       모집직종
    <wantedTitle>  구인제목
    <relJobsNm>    관련직종
    <jobCont>      ★★★ 직무내용  ← 스킬 추출의 주 대상
    <certificate>  자격면허       ← 필수 요건
    <major>        전공
    <forLang>      외국어
    <compAbl>      컴퓨터활용능력  ← 우대
    <pfCond>       우대조건       ← 우대
    <etcPfCond>    기타우대조건    ← 우대
    <etcHopeCont>  기타안내
    <selMthd> <rcptMthd> <submitDoc>      전형/접수/제출서류
    <receiptCloseDt> <empTpNm> <collectPsncnt>
    <salTpNm> <enterTpNm> <eduNm>
    <workRegion> <indArea> <nearLine> <workdayWorkhrCont>
    <fourIns> <retirepay> <etcWelfare> <disableCvntl>
    <attachFileInfo><attachFileUrl>        회사소개 첨부
    <keywordList><srchKeywordNm>           ★ 워크넷이 부여한 키워드
    <dtlRecrContUrl>                       상세모집내용 URL
    <jobsCd> <minEdubgIcd> <maxEdubgIcd> <regionCd>
    <empTpCd> <enterTpCd> <salTpCd>        코드값들
    <staAreaRegionCd> <lineCd> <staNmCd> <exitNoCd> <walkDistCd>
  </wantedInfo>
  <empchargeInfo>                          ⚠️ 개인정보 — 저장 금지
    <empChargerDpt> <contactTelno> <empChargerHp> <chargerFaxNo> <chargerEmail>
  </empchargeInfo>
</wantedDtl>
```

### 4.3 코드값
| 코드 | 값 |
|---|---|
| 학력 (`minEdubgIcd`) | `00` 무관 `01` 초졸이하 `02` 중졸 `03` 고졸 `04` 대졸(2~3년) `05` 대졸(4년) `06` 석사 `07` 박사 |
| 경력 (`enterTpCd`) | `N` 신입 `E` 경력 `Z` 관계없음 |
| 임금형태 (`salTpCd`) | `D` 일급 `H` 시급 `M` 월급 `Y` 연봉 |
| 고용형태 (`empTpCd`) | `10` 기간의 정함 없음 `11` 〃(시간선택제) `20` 기간의 정함 있음 … |

직종·지역 코드표는 엑셀로 제공 → `data/work24_codes/jobs.xls`, `region.xls` 에 저장 완료.
(출처: `https://openapi.work.go.kr/opi/opi/common/useApi/apiCdList.do?cdGbn=jobs|region`)

---

## 5. 작업 1.1의 5개 질문 — 답변

| # | 질문 | 답 |
|---|---|---|
| 1 | 상세 API에 본문 텍스트가 있는가? | ✅ **있다.** `jobCont`(직무내용) 중심으로 `certificate`·`pfCond`·`etcPfCond`·`compAbl` |
| 2 | 1회 최대 건수 / 페이징 깊이 | `display` 최대 **100**, `startPage` 최대 **1000** → 조건당 10만 건 |
| 3 | 증분 수집 가능한가? | ✅ `regDate`(D-0~M-1) 또는 `minWantedAuthDt`/`maxWantedAuthDt` 범위 |
| 4 | IT 직종 필터 가능한가? | ✅ `occupation` 파라미터. **실제 건수는 API 승인 후 측정 필요** |
| 5 | 일일 호출 한도 | ❓ 명세에 없음. 실측 또는 문의 필요 |

---

## 6. 설계에 미치는 영향 ★

### 6.1 좋은 소식 — 섹션 분리 작업이 거의 사라진다
당초 설계는 "공고 본문이 자유 서술이니 자격요건/우대사항 섹션을 정규식으로 쪼갠다"였다(작업 1.6).
그런데 **API가 이미 필드로 나눠서 준다.**

| 우리 설계의 `sections` | 대응 필드 |
|---|---|
| `main_tasks` | `jobCont` |
| `requirements` | `certificate`, `major`, `forLang`, `eduNm`, `enterTpNm` |
| `preferred` | `pfCond`, `etcPfCond`, `compAbl` |
| `benefits` | `fourIns`, `retirepay`, `etcWelfare` |

→ **`job_skills.is_required` 판정이 훨씬 정확해진다.** 문단 위치를 추측할 필요 없이
어느 필드에서 나왔는지로 필수/우대가 결정된다.
→ 작업 1.6은 "섹션 분리"가 아니라 "필드 → 섹션 매핑"으로 축소.

### 6.2 나쁜 소식 — 상세는 건별 호출 (N+1)
목록 1회로 100건을 받지만, 본문을 얻으려면 **`wantedAuthNo` 하나씩** 상세를 호출해야 한다.
1만 건이면 **1만 번 호출**.

→ 대응:
- `content_hash` / `smodifyDtm` 으로 **변경된 공고만** 상세 재호출
- 동시성 제한 + 요청 간격 (rate limit 미상이므로 보수적으로)
- Celery 태스크를 목록/상세로 분리, 상세는 큐에 쌓아 천천히 소화

### 6.3 개인정보 — `empchargeInfo` 는 저장하지 않는다
담당자 휴대전화·이메일·팩스가 온다. **우리 서비스에 불필요하고 보관 위험만 크다.**
→ Raw 레이어 적재 시점에 **마스킹 후 저장**하거나 아예 제거한다. (정규화 단계가 아니라 수집 단계에서)

### 6.4 `companies` 테이블이 풍부해진다
`totPsncnt`(근로자수) · `capitalAmt`(자본금) · `yrSalesAmt`(연매출) · `busiSize`(회사규모) · `busiCont`(주요사업) ·
`homePg` 확보 → Phase 2 매칭 피처(기업 규모 선호)로 바로 쓸 수 있다.
`busino`(사업자등록번호)가 있어 **회사 식별이 정확**하다 (이름 정규화 매칭 불필요).

### 6.5 `keywordList` 는 공짜 라벨
워크넷이 이미 부여한 검색 키워드다. 우리 스킬 추출기의 **정답 비교군(평가셋)** 으로 쓸 수 있다.

---

## 7. 남은 확인 사항
- [ ] 채용정보 API **활용신청 승인** (현재 미승인)
- [ ] 직종코드 엑셀 파싱 → IT 관련 코드 목록 확정
- [ ] IT 직종 실제 공고 건수 측정 (Phase 1 DoD 10,000건 달성 가능성)
- [ ] 일일/초당 호출 한도 실측
- [ ] `jobCont` 의 실제 텍스트 품질 (길이 분포, 빈 값 비율)
