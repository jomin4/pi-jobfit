"""수집기 공통 계약.

파이프라인은 이 모듈의 타입만 알면 되고, 원문이 어느 소스에서 왔는지는 모른다.
새 소스를 붙일 때는 JobCollector 를 상속해 _fetch_list / _fetch_detail 만 구현한다.

설계 원칙:
    정책(호출 예산, 개인정보 제거, 해시 계산)은 **베이스가 강제**하고
    구현체는 "가져오기"만 한다. 구현체가 정책을 잊을 수 없게 만드는 게 목적이다.
"""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any, ClassVar

from jobfit.collectors.budget import CallBudget, UnlimitedBudget

# 수집 단계에서 제거할 개인정보 키.
# 고용24 상세 응답의 empchargeInfo(담당자 휴대전화/이메일/팩스)가 대상이다.
# Raw 레이어는 불변이라 한 번 들어가면 지우기 어려우므로 적재 전에 잘라낸다.
PII_KEYS: frozenset[str] = frozenset(
    {
        "empchargeInfo",
        "empChargerDpt",
        "empChargerHp",
        "chargerEmail",
        "chargerFaxNo",
        "contactTelno",
    }
)


def content_hash(payload: dict[str, Any]) -> str:
    """내용 기반 해시.

    키 순서나 공백이 달라져도 같은 내용이면 같은 해시가 나오도록 정규화 후 sha256.
    이 값이 raw_job_postings 의 중복 판정 기준이다.
    """
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def scrub_pii(value: Any) -> Any:
    """중첩 구조를 순회하며 개인정보 키를 제거한다."""
    if isinstance(value, dict):
        return {k: scrub_pii(v) for k, v in value.items() if k not in PII_KEYS}
    if isinstance(value, list):
        return [scrub_pii(v) for v in value]
    return value


@dataclass(frozen=True)
class RawDocument:
    """수집기가 돌려주는 원문 한 건. 파이프라인이 다루는 유일한 형태."""

    source: str
    source_id: str
    endpoint: str
    payload: dict[str, Any]

    @property
    def hash(self) -> str:
        return content_hash(self.payload)


@dataclass(frozen=True)
class ListQuery:
    """목록 조회 조건.

    소스마다 파라미터 이름이 다르다(고용24 occupation / 사람인 job_cd).
    그 차이를 각 구현체가 흡수하고, 호출자는 이 타입만 쓴다.
    """

    job_categories: tuple[str, ...] = ()
    regions: tuple[str, ...] = ()
    keyword: str | None = None
    published_from: date | None = None
    published_to: date | None = None
    page: int = 1
    page_size: int = 100


@dataclass(frozen=True)
class ListPage:
    """목록 조회 1페이지 결과."""

    documents: tuple[RawDocument, ...]
    total: int
    page: int
    page_size: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total


class JobCollector(ABC):
    """채용공고 수집기 인터페이스."""

    #: raw_job_postings.source 에 들어갈 값
    source: ClassVar[str]
    #: 목록 응답에 본문이 없어 건별 상세 호출이 필요한 소스인지
    supports_detail: ClassVar[bool] = True
    #: 한 번에 받을 수 있는 최대 건수 (소스 제약)
    max_page_size: ClassVar[int] = 100

    def __init__(self, budget: CallBudget | None = None) -> None:
        self._budget = budget or UnlimitedBudget()

    # ---- 구현체가 채우는 부분 --------------------------------------------

    @abstractmethod
    def _fetch_list(self, query: ListQuery) -> tuple[list[tuple[str, dict[str, Any]]], int]:
        """(source_id, payload) 목록과 전체 건수를 돌려준다."""

    @abstractmethod
    def _fetch_detail(self, source_id: str) -> dict[str, Any] | None:
        """상세 payload. 없으면 None."""

    # ---- 호출자가 쓰는 부분 (정책이 여기서 강제된다) ----------------------

    def fetch_list(self, query: ListQuery) -> ListPage:
        page_size = min(query.page_size, self.max_page_size)
        self._budget.consume(self.source)
        rows, total = self._fetch_list(query)
        docs = tuple(self._document(sid, "list", payload) for sid, payload in rows)
        return ListPage(documents=docs, total=total, page=query.page, page_size=page_size)

    def fetch_detail(self, source_id: str) -> RawDocument | None:
        if not self.supports_detail:
            return None
        self._budget.consume(self.source)
        payload = self._fetch_detail(source_id)
        if payload is None:
            return None
        return self._document(source_id, "detail", payload)

    def iter_list(self, query: ListQuery, max_pages: int = 1000) -> Iterator[RawDocument]:
        """페이징을 감춘다. 예산이 떨어지면 BudgetExceededError 가 그대로 올라온다."""
        page = query.page
        for _ in range(max_pages):
            result = self.fetch_list(_with_page(query, page))
            yield from result.documents
            if not result.has_next or not result.documents:
                return
            page += 1

    def calls_used(self) -> int:
        return self._budget.used(self.source)

    # ---- 내부 ------------------------------------------------------------

    def _document(self, source_id: str, endpoint: str, payload: dict[str, Any]) -> RawDocument:
        return RawDocument(
            source=self.source,
            source_id=source_id,
            endpoint=endpoint,
            payload=scrub_pii(payload),
        )


def _with_page(query: ListQuery, page: int) -> ListQuery:
    """frozen dataclass 라 교체본을 만든다."""
    return ListQuery(
        job_categories=query.job_categories,
        regions=query.regions,
        keyword=query.keyword,
        published_from=query.published_from,
        published_to=query.published_to,
        page=page,
        page_size=query.page_size,
    )
