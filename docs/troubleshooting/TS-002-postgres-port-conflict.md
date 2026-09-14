# TS-002. 네이티브 PostgreSQL과의 5432 포트 충돌

- **발생**: 2026-09-14 · Phase 0 · 작업 0.6b (Alembic)
- **소요**: 약 15분
- **교훈 등급**: ★★★ — 증상이 원인을 전혀 가리키지 않았던 사례

## 증상

TS-001을 해결한 직후 `alembic upgrade head` 재실행 시:

```
psycopg.OperationalError: connection failed:
connection to server at "127.0.0.1", port 5432 failed:
ġ��������:  ����� "jobfit"�� password ������ �����߽��ϴ�
```

두 가지가 이상했다.
1. `docker compose ps`는 `Up (healthy)`, 포트도 `0.0.0.0:5432->5432/tcp`로 정상
2. `.env`와 컨테이너 환경변수가 `jobfit` / `jobfit_dev`로 **완전히 일치**
3. 그런데 에러 메시지가 **깨진 한글**

## 진단 방법

**1) 설정 불일치부터 배제**
```bash
docker exec jobfit-postgres printenv | grep -i postgres
cat .env
```
→ `POSTGRES_USER=jobfit`, `POSTGRES_PASSWORD=jobfit_dev` 양쪽 동일. 설정 문제 아님.

**2) 볼륨이 예전 비밀번호로 초기화됐는지 확인**

`POSTGRES_PASSWORD`는 **데이터 디렉터리 최초 생성 시에만** 적용된다.
기존 볼륨이 남아 있으면 예전 비밀번호가 유지된다 — 가장 흔한 원인이라 먼저 의심했다.

```bash
docker volume inspect pi-recruitment-notice_pgdata --format "{{.CreatedAt}}"
docker inspect jobfit-postgres --format "{{.Created}}"
docker exec jobfit-postgres stat -c "%y" /var/lib/postgresql/data/PG_VERSION
```
```
2026-09-14T05:42:13Z     볼륨
2026-09-14T05:42:13Z     컨테이너
2026-09-14 05:42:16      DB 초기화
```
→ 셋 다 동시각. 볼륨은 깨끗함. **이 가설 기각.**

**3) 컨테이너 안/밖을 나눠서 접속 테스트 (범위 분리)**
```bash
# 컨테이너 내부 (유닉스 소켓)
docker exec jobfit-postgres psql -U jobfit -d jobfit -c "SELECT current_user;"
# → 성공

# 호스트에서 TCP
python -c "import psycopg; psycopg.connect('postgresql://jobfit:jobfit_dev@localhost:5432/jobfit')"
# → 실패
```
내부는 되고 밖은 안 된다 → **네트워크 경로상의 문제**로 범위가 좁혀짐.
(유닉스 소켓은 `trust` 인증이라 비밀번호를 검사하지 않는다는 점도 기억할 것)

**4) 결정적 단서 — 에러 메시지 언어**
```bash
docker exec jobfit-postgres psql -U jobfit -d jobfit -tAc "SHOW lc_messages;"
# en_US.utf8
```
컨테이너는 **영어** 메시지를 낸다. 그런데 우리가 받은 건 한글(깨진).
→ **응답하는 서버가 컨테이너가 아니다.**

**5) 포트 점유 프로세스 직접 확인**
```powershell
Get-NetTCPConnection -LocalPort 5432 -State Listen |
  ForEach-Object { $p = Get-Process -Id $_.OwningProcess; "$($_.LocalAddress) PID=$($_.OwningProcess) $($p.ProcessName)" }

Get-Service -Name "*postgres*"
```
```
::         PID=9040  postgres
0.0.0.0    PID=9040  postgres

Name                Status  StartType
postgresql-x64-18   Running Automatic
```
→ **Windows 네이티브 PostgreSQL 18 서비스**가 5432를 점유 중.

## 원인

`localhost:5432` 접속이 전부 **네이티브 PG18**로 갔다.
그 서버에는 `jobfit` 역할이 없으니 인증 실패.

깨진 한글은 네이티브 PG18이 **한국어 Windows 로케일(cp949)** 로 낸 에러 메시지를
psycopg가 UTF-8로 해석해서 생긴 mojibake였다. 즉 인코딩 문제가 아니라,
**"이 서버는 우리 컨테이너가 아니다"라는 증거**였다.

### 왜 Docker는 포트 바인딩에 실패하지 않았나
Linux였다면 `port is already allocated`로 즉시 실패했을 것이다.
Windows는 바인딩 규칙이 느슨해서 Docker Desktop의 프록시와 네이티브 서비스가
같은 포트에 공존할 수 있고, `docker compose ps`도 정상으로 표시된다.
**즉 "포트 충돌인데 포트 충돌 에러가 안 난다."**

### 미해결 의문 (기록용)
30분 전 `scripts/check_conn.py` 는 5432로 접속해 `pgvector v0.8.6`을 보고했다.
네이티브 PG18에는 pgvector가 없으므로, 그때는 **컨테이너에 붙었던 게 확실하다.**
즉 포트 소유권이 도중에 바뀌었다. 네이티브 서비스(StartType=Automatic)가
재시작되면서 Docker 프록시로부터 바인딩을 가져간 것으로 추정되나 확증은 없다.

→ 시사점: Windows에서 기본 포트를 쓰면 **어제 되던 게 오늘 안 될 수 있다.**
"어제는 됐는데"는 설정이 그대로임을 보장하지 않는다.

## 해결

네이티브 PG18은 다른 프로젝트에서 쓸 수 있으므로 끄지 않고, 우리 컨테이너를 옮겼다.

`.env` / `.env.example`:
```ini
POSTGRES_PORT=5433
```

`docker-compose.yml`은 이미 `"${POSTGRES_PORT:-5432}:5432"` 형태라 수정 불필요.
호스트 5433 → 컨테이너 5432로 매핑되고, `config.py`의 `database_url`도
같은 변수를 읽으므로 클라이언트 쪽도 자동으로 맞는다.

```bash
docker compose up -d
```

검증:
```
0.0.0.0:5433->5432/tcp
[OK] Postgres : PostgreSQL 16.15 (Debian ...)
[OK] pgvector : v0.8.6
[OK] Redis    : ok
0001 (head)
```

## 재발 방지

**1) 컨테이너 포트는 처음부터 기본값을 피한다**
Postgres 5432, Redis 6379, MySQL 3306 같은 기본 포트는 이미 뭔가 쓰고 있을 확률이 높다.
Phase 5 이후 추가될 서비스도 비표준 포트로 매핑한다 (MLflow 5000, Grafana 3000 등 주의).

**2) 접속 문제는 항상 "누가 그 포트에 있는가"부터 본다**
```powershell
Get-NetTCPConnection -LocalPort <포트> -State Listen |
  ForEach-Object { (Get-Process -Id $_.OwningProcess).ProcessName }
```

**3) 서버가 내는 메타정보를 신원 확인에 쓴다**
`lc_messages`, `SELECT version()`, 포트, 인코딩 — 예상과 다르면
설정이 틀린 게 아니라 **다른 서버에 붙은 것**을 먼저 의심한다.

**4) 컨테이너 안/밖을 나눠 테스트하는 습관**
- 안에서 되고 밖에서 안 됨 → 네트워크/포트/방화벽
- 안에서도 안 됨 → DB 설정/권한/데이터
범위를 절반으로 줄이는 가장 빠른 방법이다.

**5) 운영(Oracle ARM, Linux) 배포 시 참고**
Linux에서는 이 문제가 명시적 에러로 나므로 오히려 안전하다.
다만 k3s에서는 호스트 포트를 쓰지 않고 Service/Ingress로 접근하므로
`POSTGRES_PORT`는 환경별로 달라진다 — `.env`로 분리해둔 게 이래서 중요하다.
