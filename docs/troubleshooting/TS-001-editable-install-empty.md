# TS-001. editable 설치가 빈 껍데기로 남는 문제

- **발생**: 2026-09-14 · Phase 0 · 작업 0.6b (Alembic)
- **소요**: 약 10분

## 증상

`alembic upgrade head` 실행 시, `migrations/env.py`의 import 줄에서 실패.

```
File "C:\...\migrations\env.py", line 9, in <module>
    from jobfit.config import settings
ModuleNotFoundError: No module named 'jobfit'
```

`uv pip install -e ".[dev]"` 는 분명히 에러 없이 끝났고, `uv pip show jobfit` 도 패키지가 설치됐다고 표시함.

## 오진했던 것

- "가상환경이 활성화 안 됐나" → `sys.prefix`가 `.venv`를 가리켜서 아님
- "alembic이 프로젝트 루트를 sys.path에 안 넣나" → `prepend_sys_path = .` 이미 설정됨
  (실제로는 src-layout이라 루트를 넣어도 `jobfit`을 못 찾는 게 맞음)

## 진단 방법

**1) 실제로 import 되는지 직접 확인**
```bash
.venv/Scripts/python.exe -c "import jobfit; print(jobfit.__file__)"
```
→ `ModuleNotFoundError`. alembic 문제가 아니라 **설치 자체의 문제**로 범위가 좁혀짐.

**2) site-packages에 경로 연결 파일(.pth)이 있는지 확인**
```bash
ls .venv/Lib/site-packages | grep -i "jobfit|editable|.pth"
```
```
_virtualenv.pth
a1_coverage.pth
jobfit-0.1.0.dist-info/     ← 메타데이터만 있고 .pth 가 없음
```

**3) 무엇이 설치됐는지 RECORD로 확인 (결정적)**
```bash
cat .venv/Lib/site-packages/jobfit-0.1.0.dist-info/RECORD
```
```
jobfit-0.1.0.dist-info/INSTALLER,...
jobfit-0.1.0.dist-info/METADATA,...
jobfit-0.1.0.dist-info/RECORD,,
jobfit-0.1.0.dist-info/REQUESTED,...
jobfit-0.1.0.dist-info/WHEEL,...
jobfit-0.1.0.dist-info/direct_url.json,...
jobfit-0.1.0.dist-info/uv_build.json,...
jobfit-0.1.0.dist-info/uv_cache.json,...
```
→ dist-info 파일 8개뿐. **패키지 파일도, 경로 연결도 없는 빈 설치.**

## 원인

작업 순서가 뒤집혔다.

1. 작업 0.2에서 `pyproject.toml` 작성 후 `uv pip install -e ".[dev]"` 실행
2. 작업 0.3에서 `src/jobfit/` 디렉터리 생성

`pyproject.toml`의 `[tool.hatch.build.targets.wheel] packages = ["src/jobfit"]` 가
가리키는 경로가 **설치 시점에 존재하지 않았다.** 빌드 백엔드는 넣을 파일이 없으니
메타데이터만 기록하고 정상 종료했다.

editable 설치는 **설치 시점의 디렉터리 구조를 기준으로 링크를 만든다.**
나중에 패키지 디렉터리를 만들어도 자동으로 따라오지 않는다.

## 해결

```bash
uv pip uninstall jobfit
uv pip install -e ".[dev]" --no-cache
```

`--no-cache`가 필수. uv가 이전의 빈 빌드 결과를 캐시에 갖고 있어서,
생략하면 같은 껍데기를 그대로 다시 설치한다.

검증:
```bash
python -c "import jobfit; print(jobfit.__file__)"
# C:\Users\kdcho\Desktop\pi-recruitment-notice\src\jobfit\__init__.py
```

## 재발 방지

**1) 아래 상황에서는 반드시 재설치한다**
- `pyproject.toml`의 `packages` / `dependencies` 를 수정했을 때
- `src/` 아래에 **최상위 패키지**를 새로 만들었을 때 (하위 모듈 추가는 괜찮음)

**2) `alembic.ini`에 안전장치 추가** — 패키지가 설치돼 있지 않아도 동작하도록

```ini
prepend_sys_path = . src
path_separator = space
```

`path_separator`를 `os`에서 `space`로 바꾸는 이유: `os`는 Windows에서 `;`,
Linux에서 `:`로 달라진다. 로컬(Windows)과 운영(Linux ARM)이 **같은 설정 파일**을
써야 하므로 OS 독립적인 공백 구분자를 쓴다.

**3) 앞으로 "설치했는데 import가 안 된다"면 RECORD부터 본다.**
`uv pip show`는 메타데이터만 보므로 빈 설치를 걸러내지 못한다.
