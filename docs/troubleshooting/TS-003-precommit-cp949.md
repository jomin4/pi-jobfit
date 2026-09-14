# TS-003. pre-commit 설정 파일의 한글 주석이 cp949로 깨지는 문제

- **발생**: 2026-09-14 · Phase 0 · 작업 0.8 (코드 품질 자동화)
- **소요**: 약 10분
- 한 작업에서 연달아 나온 4가지 함정을 함께 기록한다.

---

## 문제 1 — `pre-commit autoupdate` 가 UnicodeDecodeError

### 증상
```
An unexpected error has occurred: UnicodeDecodeError:
'cp949' codec can't decode byte 0xec in position 18: illegal multibyte sequence
```

`.pre-commit-config.yaml` 에 한글 주석을 넣었더니 발생.

### 원인
- **TOML은 표준이 UTF-8을 강제**한다. 그래서 `pyproject.toml`의 한글 주석은 멀쩡했다.
- **YAML은 그런 강제가 없다.** pre-commit이 `open()` 기본 인코딩으로 읽는데,
  한국어 Windows의 기본값은 **cp949**라서 UTF-8 한글 바이트를 해석하지 못한다.

같은 한글 주석인데 한 파일은 되고 한 파일은 안 되는 이유가 여기 있다.

### 해결
`.pre-commit-config.yaml` 을 **ASCII 전용**으로 작성한다.
설명이 필요하면 영어로 쓰거나 문서로 뺀다.

### 일반화
**서드파티 도구가 읽는 설정 파일에는 non-ASCII를 넣지 않는다.**
우리 코드는 인코딩을 우리가 통제하지만, 남의 도구가 어떻게 읽을지는 통제할 수 없다.
`pyproject.toml`(TOML), 우리 파이썬 소스(UTF-8 기본)는 한글 주석 OK.

---

## 문제 2 — 훅 버전(rev)을 손으로 적으면 낡는다

처음 적은 값과 `pre-commit autoupdate` 결과:

| 저장소 | 처음 적은 rev | 실제 최신 |
|---|---|---|
| pre-commit-hooks | v5.0.0 | **v6.0.0** |
| ruff-pre-commit | v0.8.0 | **v0.16.7** |

존재하지 않는 rev면 훅 설치 자체가 실패한다.

### 해결
설정 파일을 만든 직후 항상 실행한다.
```bash
pre-commit autoupdate
```

또한 ruff-pre-commit v0.9부터 훅 id `ruff` 는 **legacy alias**가 되었다.
실행 로그에 `ruff (legacy alias)` 가 보이면 `ruff-check` 로 바꾼다.

---

## 문제 3 — `no files to check` 로 전부 Skipped

### 증상
```
trim trailing whitespace......(no files to check)Skipped
ruff format...................(no files to check)Skipped
```

### 원인
**pre-commit은 git이 추적하는 파일만 검사한다.**
첫 커밋 전이라 모든 파일이 untracked(`??`) 상태였다.

### 해결
```bash
git add -A
pre-commit run --all-files
```

### 일반화
"검사가 통과했다"와 "검사할 게 없었다"는 다르다.
훅이 전부 `Skipped`면 통과가 아니라 **아무것도 안 본 것**이다.

---

## 문제 4 — `Executable 'mypy' not found`

### 증상
```
mypy.....................................Failed
- hook id: mypy
- exit code: 1
Executable `mypy` not found
```

### 원인
`.pre-commit-config.yaml` 에서 mypy를 `language: system` 으로 선언했다.
이건 "PATH에 있는 실행파일을 그대로 쓴다"는 뜻인데,
**가상환경을 활성화하지 않은 셸**에서 실행해서 PATH에 mypy가 없었다.

가상환경을 활성화하고 재실행하니 통과.
```bash
source .venv/Scripts/activate   # PowerShell: .\.venv\Scripts\Activate.ps1
pre-commit run --all-files
```

### 왜 그래도 `language: system` 을 쓰나
mypy는 `pydantic`, `sqlalchemy` 등 **프로젝트 의존성의 타입 정보**가 있어야
제대로 검사한다. 원격 훅(`language: python`)으로 돌리면 격리된 환경이 만들어져
그 의존성을 `additional_dependencies` 에 **중복 선언**해야 하고,
버전이 어긋나면 로컬과 CI 결과가 달라진다.

트레이드오프를 받아들이고, 대신 규칙을 둔다:
> **커밋은 항상 가상환경이 활성화된 셸에서 한다.**
> CI(GitHub Actions)에서는 의존성 설치 후 실행하므로 문제가 되지 않는다.

---

## 덤 — 줄바꿈(CRLF) 경고 정리

`git add` 시 `LF will be replaced by CRLF` 경고가 40줄 넘게 쏟아졌다.
개발은 Windows(CRLF), 운영은 Linux ARM + Docker(LF)라 섞이면
셸 스크립트와 Dockerfile 엔트리포인트가 `\r` 때문에 깨진다.

`.gitattributes` 를 추가해 **저장소 기준을 LF로 고정**했다.
```
* text=auto eol=lf
*.ps1 text eol=crlf
```
적용:
```bash
git add --renormalize .
```

---

## 이번 작업의 최종 검증 결과

```
trim trailing whitespace.....Passed      ruff format....Passed
fix end of files.............Passed      ruff check.....Passed
check yaml / toml............Passed      mypy...........Passed
detect private key...........Passed
check for added large files..Passed

4 passed  (pytest)
```

## 재발 방지 체크리스트
- [ ] 서드파티 설정 파일(YAML/INI)은 ASCII로 작성
- [ ] `pre-commit autoupdate` 를 설정 직후 실행
- [ ] 훅이 `Skipped` 면 통과로 착각하지 말 것
- [ ] 커밋은 venv 활성화 상태에서
- [ ] Windows에서 한글 출력이 깨지면 `PYTHONUTF8=1`
