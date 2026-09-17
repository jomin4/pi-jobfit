"""수집기 계층 단위 테스트. 외부 호출 없이 전부 로컬에서 끝난다."""

import pytest

from jobfit.collectors.base import ListQuery, content_hash, scrub_pii
from jobfit.collectors.budget import UnlimitedBudget
from jobfit.collectors.sample import SampleCollector
from jobfit.exceptions import BudgetExceededError


class _TinyBudget(UnlimitedBudget):
    """한도 2회짜리 가짜 예산. Redis 없이 예산 로직을 검증한다."""

    def consume(self, source: str, n: int = 1) -> None:
        super().consume(source, n)
        if self.used(source) > 2:
            raise BudgetExceededError(source=source, limit=2, used=self.used(source))


def test_content_hash는_키_순서에_흔들리지_않는다() -> None:
    assert content_hash({"a": 1, "b": 2}) == content_hash({"b": 2, "a": 1})


def test_content_hash는_값이_바뀌면_달라진다() -> None:
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_개인정보_키는_중첩_구조에서도_제거된다() -> None:
    payload = {
        "wantedAuthNo": "X",
        "empchargeInfo": {"chargerEmail": "a@b.c"},
        "nested": [{"contactTelno": "02-000", "keep": 1}],
    }

    scrubbed = scrub_pii(payload)

    assert "empchargeInfo" not in scrubbed
    assert scrubbed["nested"][0] == {"keep": 1}
    assert scrubbed["wantedAuthNo"] == "X"


def test_수집기는_개인정보를_제거한_뒤_문서를_만든다() -> None:
    collector = SampleCollector(total=5)

    doc = collector.fetch_detail("SAMPLE-000000")

    assert doc is not None
    assert "empchargeInfo" not in doc.payload
    assert doc.source == "sample"
    assert doc.endpoint == "detail"


def test_같은_seed는_항상_같은_데이터를_만든다() -> None:
    a = SampleCollector(total=10, seed=42).fetch_detail("SAMPLE-000003")
    b = SampleCollector(total=10, seed=42).fetch_detail("SAMPLE-000003")

    assert a is not None and b is not None
    assert a.hash == b.hash


def test_seed가_다르면_다른_데이터가_나온다() -> None:
    a = SampleCollector(total=10, seed=42).fetch_detail("SAMPLE-000003")
    b = SampleCollector(total=10, seed=7).fetch_detail("SAMPLE-000003")

    assert a is not None and b is not None
    assert a.hash != b.hash


def test_없는_공고는_None을_돌려준다() -> None:
    collector = SampleCollector(total=5)

    assert collector.fetch_detail("SAMPLE-999999") is None
    assert collector.fetch_detail("NOT-AN-ID") is None


def test_목록은_페이징된다() -> None:
    collector = SampleCollector(total=250)

    first = collector.fetch_list(ListQuery(page=1, page_size=100))
    last = collector.fetch_list(ListQuery(page=3, page_size=100))

    assert len(first.documents) == 100
    assert first.total == 250
    assert first.has_next is True
    assert len(last.documents) == 50
    assert last.has_next is False


def test_page_size는_소스_상한을_넘지_못한다() -> None:
    collector = SampleCollector(total=300)

    page = collector.fetch_list(ListQuery(page=1, page_size=999))

    assert page.page_size == SampleCollector.max_page_size
    assert len(page.documents) == SampleCollector.max_page_size


def test_iter_list는_전체를_순회한다() -> None:
    collector = SampleCollector(total=120)

    docs = list(collector.iter_list(ListQuery(page_size=50)))

    assert len(docs) == 120
    assert len({d.source_id for d in docs}) == 120


def test_예산을_넘으면_수집이_중단된다() -> None:
    collector = SampleCollector(total=1000, budget=_TinyBudget())

    with pytest.raises(BudgetExceededError):
        list(collector.iter_list(ListQuery(page_size=10)))

    assert collector.calls_used() == 3  # 2회 성공 + 초과 1회


def test_정답_스킬은_생성_시점에_확정된다() -> None:
    collector = SampleCollector(total=5)

    truth = collector.ground_truth("SAMPLE-000001")

    assert truth is not None
    assert len(truth.required) >= 2
    assert set(truth.required).isdisjoint(truth.preferred)


def test_목록_응답은_고용24_필드명을_따른다() -> None:
    collector = SampleCollector(total=3)

    row = collector.fetch_list(ListQuery(page_size=1)).documents[0].payload

    for key in ("wantedAuthNo", "company", "title", "region", "career", "closeDt", "jobsCd"):
        assert key in row


def test_공고_날짜는_고정_기준일에서_계산된다() -> None:
    """datetime.now() 로 되돌아가면 실행마다 content_hash 가 바뀌어 멱등성이 깨진다."""
    from datetime import date, timedelta

    from jobfit.collectors.sample import SAMPLE_EPOCH

    doc = SampleCollector(total=5).fetch_detail("SAMPLE-000000")

    assert doc is not None
    posted = date.fromisoformat(doc.payload["regDt"])
    assert timedelta(0) <= SAMPLE_EPOCH.date() - posted <= timedelta(days=60)
