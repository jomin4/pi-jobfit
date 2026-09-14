"""로컬 인프라(Postgres, Redis) 연결 확인 + pgvector 확장 설치."""

import redis
from sqlalchemy import create_engine, text

from jobfit.config import settings


def check_postgres() -> None:
    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        # pgvector는 이미지에 포함돼 있지만, DB마다 한 번은 활성화해줘야 한다
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        ext_version = conn.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
    print(f"[OK] Postgres : {version.split(',')[0]}")
    print(f"[OK] pgvector : v{ext_version}")


def check_redis() -> None:
    client = redis.Redis.from_url(settings.redis_url)
    client.set("jobfit:healthcheck", "ok", ex=10)
    value = client.get("jobfit:healthcheck")
    print(f"[OK] Redis    : {value.decode()}")


if __name__ == "__main__":
    check_postgres()
    check_redis()
