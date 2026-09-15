"""외부 API 일일 호출 예산.

외부가 정한 한도를 코드가 모르면 언젠가 반드시 넘긴다.
그래서 수집기는 예산 객체를 반드시 하나 들고 다닌다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime

from redis import Redis

from jobfit.exceptions import BudgetExceededError


class CallBudget(ABC):
    """호출 1회를 쓰기 전에 허락을 받는 관문."""

    @abstractmethod
    def consume(self, source: str, n: int = 1) -> None:
        """n회를 소비한다. 한도를 넘으면 BudgetExceededError 를 던진다."""

    @abstractmethod
    def used(self, source: str) -> int:
        """오늘 사용한 호출 수."""


class UnlimitedBudget(CallBudget):
    """한도가 없는 예산. 샘플 수집기와 테스트에서 쓴다."""

    def __init__(self) -> None:
        self._counter: dict[str, int] = {}

    def consume(self, source: str, n: int = 1) -> None:
        self._counter[source] = self._counter.get(source, 0) + n

    def used(self, source: str) -> int:
        return self._counter.get(source, 0)


class RedisDailyBudget(CallBudget):
    """Redis 카운터 기반 일일 예산.

    키는 날짜별로 분리되고 TTL 로 자동 소멸하므로 초기화 로직이 필요 없다.
    워커가 여러 개여도 INCRBY 가 원자적이라 합계가 어긋나지 않는다.
    """

    KEY_TEMPLATE = "jobfit:budget:{source}:{day}"
    TTL_SECONDS = 60 * 60 * 26  # 하루 + 여유 2시간

    def __init__(self, client: Redis, limit: int) -> None:
        self._client = client
        self._limit = limit

    def _key(self, source: str) -> str:
        day = datetime.now(UTC).strftime("%Y%m%d")
        return self.KEY_TEMPLATE.format(source=source, day=day)

    def consume(self, source: str, n: int = 1) -> None:
        key = self._key(source)
        # 먼저 올리고 초과면 되돌린다. 확인 후 증가는 경쟁 상태가 생긴다.
        used = int(self._client.incrby(key, n))
        if used == n:
            self._client.expire(key, self.TTL_SECONDS)
        if used > self._limit:
            self._client.decrby(key, n)
            raise BudgetExceededError(source=source, limit=self._limit, used=used - n)

    def used(self, source: str) -> int:
        raw = self._client.get(self._key(source))
        return int(raw) if raw else 0
