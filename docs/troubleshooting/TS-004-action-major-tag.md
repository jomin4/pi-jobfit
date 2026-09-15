# TS-004. GitHub Action에 이동 major 태그가 없어서 워크플로가 즉시 실패

- **발생**: 2026-09-14 · Phase 0 · 작업 0.9 (GitHub Actions CI)
- **소요**: 약 5분

## 증상

첫 push 후 CI가 **6초 만에** 실패. 테스트가 아니라 `Set up job` 단계에서 죽었다.

```
X Lint / Typecheck / Unit in 2s
  X Set up job
X Integration (Postgres + Redis) in 2s
  X Set up job

ANNOTATIONS
X Unable to resolve action `astral-sh/setup-uv@v10`, unable to find version `v10`
```

## 진단 방법

**1) 실패가 "얼마나 빨리" 났는지를 먼저 본다**

6초 = 코드를 체크아웃하기도 전. 테스트/의존성 문제일 리가 없다.
→ **워크플로 자체를 해석하는 단계**의 문제로 범위가 좁혀진다.

| 실패까지 걸린 시간 | 의심할 곳                         |
| ------------------ | --------------------------------- |
| ~5초               | YAML 문법, 액션 해석 실패         |
| ~30초              | 의존성 설치, 서비스 컨테이너 기동 |
| 1분+               | 실제 lint/type/test               |

**2) `--log-failed` 보다 `gh run view` 의 ANNOTATIONS 를 먼저 본다**

`--log-failed` 는 러너 부팅 로그부터 쏟아내서 정작 원인이 안 보인다.
ANNOTATIONS 섹션에 한 줄로 정리돼 있었다.

**3) 실제로 존재하는 태그를 확인**

```bash
gh api repos/astral-sh/setup-uv/tags --jq ".[].name" | head -12
```

```
v10.1.0 v10.0.1 v10.0.0 v9.0.0 v8.3.2 ... v7.6
```

비교:

```bash
gh api repos/actions/checkout/tags --jq ".[].name" | head -12
```

```
v7.0.1 v7.0.0 v7 v6.1.0 ... v6 ...
```

## 원인

`actions/checkout` 은 릴리스할 때마다 **`v7` 이라는 이동(moving) 태그**를 최신 v7.x로 옮겨준다.
그래서 `@v7` 로 쓰면 패치 업데이트를 자동으로 받는다.

**`astral-sh/setup-uv` 는 그런 이동 태그를 발행하지 않는다.** `v10` 태그가 아예 없으므로
`@v10` 은 존재하지 않는 참조가 되어 해석 실패.

> 이동 major 태그는 **GitHub의 규칙이 아니라 각 액션 저자의 관례**다.
> 공식 `actions/*` 는 대부분 제공하고, 서드파티는 제각각이다.

## 해결

```yaml
- uses: astral-sh/setup-uv@v10.1.0   # 이동 태그 없음 → 정확한 버전 고정
- uses: actions/checkout@v7          # 이동 태그 있음 → major만 써도 됨
- uses: actions/setup-python@v7
```

## 함께 발견한 것 — 버전이 통째로 낡아 있었다

처음 작성했던 값과 실제 최신:

| 액션                 | 처음 | 최신              |
| -------------------- | ---- | ----------------- |
| actions/checkout     | v4   | **v7**      |
| actions/setup-python | v5   | **v7**      |
| astral-sh/setup-uv   | v5   | **v10.1.0** |

[TS-003](TS-003-precommit-cp949.md)의 pre-commit rev와 똑같은 패턴이다.

### 재발 방지

**외부 도구의 버전은 손으로 적지 말고 조회해서 적는다.**

```bash
gh api repos/<owner>/<repo>/releases/latest --jq .tag_name   # 최신 릴리스
gh api repos/<owner>/<repo>/tags --jq ".[].name" | head      # 이동 태그 존재 여부
```

릴리스 최신 버전만 보면 안 된다. **이동 태그가 있는지까지 확인**해야 `@v10` 을 쓸 수 있는지 알 수 있다.

### 보안 관점 (참고)

가장 엄격하게 하려면 커밋 SHA로 고정한다.

```yaml
- uses: actions/checkout@8f4b7f8...   # 태그가 바뀌어도 코드가 안 바뀜
```

태그는 저자가 다른 커밋으로 옮길 수 있어 공급망 공격 표면이 된다.
다만 업데이트가 번거로워, 개인 프로젝트에서는 태그 고정으로 충분하다고 판단했다.

## 최종 결과

```
✓ Integration (Postgres + Redis)  30s
✓ Lint / Typecheck / Unit         21s
```
