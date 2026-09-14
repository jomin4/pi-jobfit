"""JobFit API 진입점."""

from typing import Literal

import redis
from fastapi import FastAPI, Response, status
from sqlalchemy import text

from jobfit.config import settings
from jobfit.db.base import engine

app = FastAPI(
    title="JobFit API",
    description="채용공고 기반 커리어 매칭",
    version="0.1.0",
)

_redis = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=2)


def _check_db() -> Literal["ok", "down"]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return "down"
    return "ok"


def _check_redis() -> Literal["ok", "down"]:
    try:
        _redis.ping()
    except Exception:
        return "down"
    return "ok"


@app.get("/health", tags=["system"])
def health(response: Response) -> dict[str, str]:
    """의존 컴포넌트 상태까지 확인하는 헬스체크.

    하나라도 down이면 503을 반환한다 — 로드밸런서가 트래픽을 안 보내도록.
    """
    checks = {"db": _check_db(), "redis": _check_redis()}
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", **checks}
