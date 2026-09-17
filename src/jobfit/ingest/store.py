"""원문 적재. 수집기가 가져온 RawDocument 를 raw_job_postings 에 넣는다.

Celery 는 나중에 이 함수를 호출만 한다. 적재 로직과 큐 배선을 분리해 두면
"수집이 틀렸나 / 큐가 틀렸나" 를 따로 디버깅할 수 있다.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from jobfit.collectors.base import JobCollector, ListQuery, RawDocument
from jobfit.db.models import IngestionRun, RawJobPosting
from jobfit.exceptions import BudgetExceededError

SessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class StoreResult:
    """적재 1회 결과. 여러 배치를 더할 수 있게 __add__ 를 둔다."""

    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0

    def __add__(self, other: StoreResult) -> StoreResult:
        return StoreResult(
            self.fetched + other.fetched,
            self.inserted + other.inserted,
            self.duplicates + other.duplicates,
        )


@dataclass
class RunHandle:
    """수집 실행 1건의 누적 상태."""

    run_id: int
    result: StoreResult = field(default_factory=StoreResult)
    api_calls: int = 0

    def add(self, result: StoreResult) -> None:
        self.result = self.result + result


def store_documents(session: Session, documents: Sequence[RawDocument]) -> StoreResult:
    """원문을 적재한다. 이미 같은 내용이 있으면 조용히 건너뛴다.

    멱등성은 애플리케이션이 아니라 uq_raw_source_hash 제약이 보장한다.
    태스크가 몇 번 재실행돼도 중복이 생기지 않는 근거가 이 한 줄이다.
    """
    # 같은 배치 안의 중복을 먼저 접는다. DB에 맡겨도 되지만 의도를 코드에 남긴다.
    unique: dict[tuple[str, str, str], RawDocument] = {}
    for doc in documents:
        unique.setdefault((doc.source, doc.source_id, doc.hash), doc)
    if not unique:
        return StoreResult()

    rows: list[dict[str, Any]] = [
        {
            "source": d.source,
            "source_id": d.source_id,
            "endpoint": d.endpoint,
            "payload": d.payload,
            "content_hash": d.hash,
        }
        for d in unique.values()
    ]

    stmt = (
        insert(RawJobPosting)
        .values(rows)
        .on_conflict_do_nothing(constraint="uq_raw_source_hash")
        .returning(RawJobPosting.id)
    )
    inserted = len(session.execute(stmt).scalars().all())
    return StoreResult(
        fetched=len(documents),
        inserted=inserted,
        duplicates=len(documents) - inserted,
    )


@contextmanager
def ingestion_run(session_factory: SessionFactory, source: str) -> Iterator[RunHandle]:
    """수집 실행의 시작과 끝을 ingestion_runs 에 남긴다.

    본문 세션과 분리된 세션을 쓴다. 적재가 롤백돼도 "실패했다"는 기록은 남아야 한다.
    """
    with session_factory() as session:
        run = IngestionRun(source=source, status="running")
        session.add(run)
        session.commit()
        run_id = run.id

    handle = RunHandle(run_id=run_id)
    status = "success"
    detail: dict[str, Any] | None = None
    try:
        yield handle
    except BudgetExceededError as exc:
        # 재시도로 해결되지 않는다. 상태를 구분해 두면 다음 날 재개 판단이 쉬워진다.
        status, detail = "budget", {"message": str(exc), "limit": exc.limit}
        raise
    except Exception as exc:
        status = "failed"
        detail = {
            "type": type(exc).__name__,
            "message": str(exc),
            "trace": traceback.format_exc()[-2000:],
        }
        raise
    finally:
        with session_factory() as session:
            session.execute(
                update(IngestionRun)
                .where(IngestionRun.id == run_id)
                .values(
                    status=status,
                    finished_at=func.now(),
                    fetched_count=handle.result.fetched,
                    new_count=handle.result.inserted,
                    error_count=0 if status == "success" else 1,
                    api_calls=handle.api_calls,
                    error_detail=detail,
                )
            )
            session.commit()


def run_ingestion(
    collector: JobCollector,
    session_factory: SessionFactory,
    query: ListQuery | None = None,
    *,
    max_pages: int = 100,
    with_detail: bool = True,
    batch_size: int = 200,
) -> RunHandle:
    """목록을 순회하며 원문을 적재한다. Celery 태스크가 그대로 호출할 함수."""
    query = query or ListQuery()
    with ingestion_run(session_factory, collector.source) as handle:
        batch: list[RawDocument] = []
        for doc in collector.iter_list(query, max_pages=max_pages):
            batch.append(doc)
            if with_detail and collector.supports_detail:
                detail = collector.fetch_detail(doc.source_id)
                if detail is not None:
                    batch.append(detail)
            handle.api_calls = collector.calls_used()
            if len(batch) >= batch_size:
                _flush(session_factory, handle, batch)
                batch = []
        _flush(session_factory, handle, batch)
        handle.api_calls = collector.calls_used()
    return handle


def _flush(session_factory: SessionFactory, handle: RunHandle, batch: list[RawDocument]) -> None:
    """배치 단위로 커밋한다. 중간에 죽어도 그때까지 넣은 건 남는다."""
    if not batch:
        return
    with session_factory() as session:
        handle.add(store_documents(session, batch))
        session.commit()
