"""raw_job_postings 의 미처리 원문을 정규화해 jobs / companies 에 적재한다.

    python scripts/normalize_sample.py
    python scripts/normalize_sample.py --reset --limit 500

미처리분만 집어오므로 여러 번 돌려도 이어받기가 된다.
가져오는 조건(processed_at IS NULL)은 ix_raw_unprocessed 부분 인덱스와 정확히 일치한다.
"""

import argparse
import sys
import time

from sqlalchemy import delete, func, select, update

from jobfit.db.base import SessionLocal
from jobfit.db.models import Company, Job, RawJobPosting
from jobfit.processing.loader import load_normalized
from jobfit.processing.normalize import normalize_details


def reset(source: str) -> None:
    """적재분을 지우고 원문을 미처리로 되돌린다. 재처리 실험용."""
    with SessionLocal() as session:
        session.execute(delete(Job).where(Job.source == source))
        session.execute(
            update(RawJobPosting).where(RawJobPosting.source == source).values(processed_at=None)
        )
        # 공고가 사라진 회사는 남겨둔다 (다른 소스가 참조할 수 있다)
        session.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="원문 정규화 및 적재")
    parser.add_argument("--source", default="sample")
    parser.add_argument("--limit", type=int, default=5000, help="한 번에 처리할 원문 수")
    parser.add_argument("--reset", action="store_true", help="적재분 삭제 후 처음부터")
    args = parser.parse_args()

    if args.reset:
        reset(args.source)
        print(f"[reset] {args.source} 적재분 삭제 및 미처리 복원")

    started = time.perf_counter()
    with SessionLocal() as session:
        pending = session.execute(
            select(RawJobPosting.id, RawJobPosting.source_id, RawJobPosting.payload)
            .where(
                RawJobPosting.source == args.source,
                RawJobPosting.endpoint == "detail",
                RawJobPosting.processed_at.is_(None),
            )
            .order_by(RawJobPosting.fetched_at)
            .limit(args.limit)
        ).all()

    if not pending:
        print("처리할 원문이 없습니다.")
        return 0

    payloads = [payload for _, _, payload in pending]
    normalized = normalize_details(args.source, payloads)

    with SessionLocal() as session:
        outcome = load_normalized(session, normalized.jobs, normalized.companies)
        # 상세뿐 아니라 같은 공고의 목록 행도 처리 완료로 표시한다.
        # 남겨두면 부분 인덱스가 영원히 줄지 않는다.
        session.execute(
            update(RawJobPosting)
            .where(
                RawJobPosting.source == args.source,
                RawJobPosting.source_id.in_([sid for _, sid, _ in pending]),
            )
            .values(processed_at=func.now())
        )
        session.commit()

    elapsed = time.perf_counter() - started

    with SessionLocal() as session:
        remaining = session.execute(
            select(func.count())
            .select_from(RawJobPosting)
            .where(
                RawJobPosting.source == args.source,
                RawJobPosting.processed_at.is_(None),
            )
        ).scalar_one()
        total_jobs = session.execute(
            select(func.count()).select_from(Job).where(Job.source == args.source)
        ).scalar_one()
        total_companies = session.execute(select(func.count()).select_from(Company)).scalar_one()

    print(f"원문 처리      : {len(pending)}")
    print(f"계약 위반 제외 : {normalized.dropped}")
    print(f"신규 / 갱신    : {outcome.inserted} / {outcome.updated}")
    print(f"변경 없음      : {outcome.skipped}")
    print(f"회사           : {outcome.companies}")
    print(f"소요           : {elapsed:.1f}초")
    print(f"남은 미처리    : {remaining}")
    print(f"테이블 현황    : jobs={total_jobs}, companies={total_companies}")

    low = sorted(normalized.fill_rate.items(), key=lambda kv: kv[1])[:5]
    print("채움 비율 하위 : " + ", ".join(f"{k} {v:.0%}" for k, v in low))
    return 0


if __name__ == "__main__":
    sys.exit(main())
