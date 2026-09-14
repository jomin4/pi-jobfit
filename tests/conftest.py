"""pytest 공통 픽스처."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from jobfit.api.main import app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """FastAPI 테스트 클라이언트.

    실제 서버(uvicorn)를 띄우지 않고 앱 객체를 직접 호출하므로 매우 빠르다.
    """
    with TestClient(app) as test_client:
        yield test_client
