"""도메인 예외. API 레이어에서 HTTP 상태코드로 변환한다."""


class JobfitError(Exception):
    """이 프로젝트의 모든 예외의 부모."""


class CollectorError(JobfitError):
    """수집 중 발생한 오류."""


class SourceUnavailableError(CollectorError):
    """외부 소스가 응답하지 않거나 권한이 없다."""


class BudgetExceededError(CollectorError):
    """일일 API 호출 한도를 초과했다.

    재시도로 해결되지 않으므로 태스크는 즉시 중단하고 다음 날로 미뤄야 한다.
    """

    def __init__(self, source: str, limit: int, used: int) -> None:
        super().__init__(f"{source}: 일일 호출 한도 초과 ({used}/{limit})")
        self.source = source
        self.limit = limit
        self.used = used
