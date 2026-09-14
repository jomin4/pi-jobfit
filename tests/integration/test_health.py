"""헬스체크 엔드포인트 통합 테스트."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_health가_db와_redis_상태를_보고한다(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "redis": "ok"}


def test_openapi_스펙에_health가_등록된다(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
