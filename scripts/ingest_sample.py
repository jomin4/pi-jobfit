"""샘플 공고를 수집해 raw_job_postings 에 적재한다.

python scripts/ingest_sample.py --total 300 --reset
python scripts/ingest_sample.py --total 2500
"""

import argparse
import sys
import time

from sqlalchemy import delete, func, select

from jobfit.collectors.base import ListQuery
from jobfit.collectors.sample import SampleCollector
from jobfit.db.base import SessionLocal
from jobfit.db.models import IngestionRun, RawJobPosting
from jobfit.ingest.store import run_ingestion


def reset_sample() -> None:
    with SessionLocal() as session:
        session.execute(delete(RawJobPosting).where(RawJobPosting.source == "sample"))
        session.execute(delete(IngestionRun).where(IngestionRun.source == "sample"))
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="샘플 공고 수집 및 적재")
    parser.add_argument("--total", type=int, default=300, help="생성할 공고 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-detail", action="store_true", help="상세 호출 생략")
    parser.add_argument("--reset", action="store_true", help="기존 sample 데이터 삭제")
    args = parser.parse_args()

    if args.reset:
        reset_sample()
        print("[reset] 기존 sample 데이터 삭제")

    collector = SampleCollector(total=args.total, seed=args.seed)
    started = time.perf_counter()
    handle = run_ingestion(
        collector,
        SessionLocal,
        ListQuery(page_size=100),
        with_detail=not args.no_detail,
    )
    elapsed = time.perf_counter() - started

    with SessionLocal() as session:
        stored = session.execute(
            select(RawJobPosting.endpoint, func.count())
            .where(RawJobPosting.source == "sample")
            .group_by(RawJobPosting.endpoint)
            .order_by(RawJobPosting.endpoint)
        ).all()

    result = handle.result
    print(f"run_id       : {handle.run_id}")
    print(f"가져온 문서   : {result.fetched}")
    print(f"신규 적재     : {result.inserted}")
    print(f"중복 건너뜀   : {result.duplicates}")
    print(f"API 호출      : {handle.api_calls}")
    print(f"소요          : {elapsed:.1f}초")
    print("테이블 현황   : " + ", ".join(f"{ep}={n}" for ep, n in stored))
    return 0


if __name__ == "__main__":
    sys.exit(main())
