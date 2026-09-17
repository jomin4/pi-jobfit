"""원문 적재 통합 테스트. 실제 Postgres 가 필요하다."""

from collections.abc import Iterator

import pytest
from sqlalchemy import delete, func, select

from jobfit.collectors.base import ListQuery
from jobfit.collectors.budget import UnlimitedBudget
from jobfit.collectors.sample import SampleCollector
from jobfit.db.base import SessionLocal
from jobfit.db.models import IngestionRun, RawJobPosting
from jobfit.exceptions import BudgetExceededError
from jobfit.ingest.store import run_ingestion, store_documents

pytestmark = pytest.mark.integration

SOURCE = "sample"


def _clear() -> None:
    with SessionLocal() as session:
        session.execute(delete(RawJobPosting).where(RawJobPosting.source == SOURCE))
        session.execute(delete(IngestionRun).where(IngestionRun.source == SOURCE))
        session.commit()


@pytest.fixture
def clean_db() -> Iterator[None]:
    _clear()
    yield
    _clear()


def _count() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count()).select_from(RawJobPosting).where(RawJobPosting.source == SOURCE)
        ).scalar_one()


def test_같은_문서를_두_번_적재해도_중복이_생기지_않는다(clean_db: None) -> None:
    docs = list(SampleCollector(total=10).iter_list(ListQuery(page_size=10)))

    with SessionLocal() as session:
        first = store_documents(session, docs)
        session.commit()
    with SessionLocal() as session:
        second = store_documents(session, docs)
        session.commit()

    assert first.inserted == 10
    assert second.inserted == 0
    assert second.duplicates == 10
    assert _count() == 10


def test_수집을_두_번_돌려도_행_수가_늘지_않는다(clean_db: None) -> None:
    for _ in range(2):
        run_ingestion(SampleCollector(total=20), SessionLocal, ListQuery(page_size=10))

    # 목록 20 + 상세 20
    assert _count() == 40


def test_실행_이력이_기록된다(clean_db: None) -> None:
    handle = run_ingestion(SampleCollector(total=15), SessionLocal, ListQuery(page_size=10))

    with SessionLocal() as session:
        run = session.get(IngestionRun, handle.run_id)
        assert run is not None
        assert run.status == "success"
        assert run.finished_at is not None
        assert run.fetched_count == 30
        assert run.new_count == 30
        assert run.error_count == 0
        assert run.api_calls > 0


def test_예산을_넘기면_실패가_아니라_budget_으로_기록된다(clean_db: None) -> None:
    class _TinyBudget(UnlimitedBudget):
        def consume(self, source: str, n: int = 1) -> None:
            super().consume(source, n)
            if self.used(source) > 3:
                raise BudgetExceededError(source=source, limit=3, used=self.used(source))

    collector = SampleCollector(total=500, budget=_TinyBudget())

    with pytest.raises(BudgetExceededError):
        run_ingestion(collector, SessionLocal, ListQuery(page_size=10))

    with SessionLocal() as session:
        run = (
            session.execute(
                select(IngestionRun)
                .where(IngestionRun.source == SOURCE)
                .order_by(IngestionRun.id.desc())
            )
            .scalars()
            .first()
        )

    # 예외가 위로 올라갔어도 "무슨 일이 있었는지"는 남아야 한다
    assert run is not None
    assert run.status == "budget"
    assert run.error_detail is not None
    assert run.finished_at is not None
