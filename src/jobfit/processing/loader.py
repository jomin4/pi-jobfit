"""정규화된 프레임을 companies / jobs 테이블에 적재한다.

회사를 먼저 넣어 id 를 확보하고, 그 id 를 공고에 붙여 UPSERT 한다.
순서를 바꾸면 company_id 가 가리킬 곳이 없다.

변경 감지는 content_hash 로 한다. 내용이 그대로면 UPDATE 도 하지 않는다 —
updated_at 만 바뀌는 무의미한 쓰기가 인덱스를 갱신시키기 때문이다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import polars as pl
from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from jobfit.collectors.base import content_hash
from jobfit.db.models import Company, Job

BATCH_SIZE = 500

# 이 필드들이 바뀌면 "내용이 달라졌다"로 본다.
# company_id 는 뺀다 — DB 상태에 따라 달라질 뿐 공고 내용이 아니다.
CONTENT_FIELDS = (
    "title",
    "description",
    "sections",
    "job_category",
    "employment_type",
    "exp_min",
    "exp_max",
    "education",
    "salary_min",
    "salary_max",
    "salary_raw",
    "region_code",
    "region_name",
    "posted_at",
    "deadline",
    "url",
)


@dataclass(frozen=True)
class LoadResult:
    companies: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0

    def __add__(self, other: LoadResult) -> LoadResult:
        return LoadResult(
            self.companies + other.companies,
            self.inserted + other.inserted,
            self.updated + other.updated,
            self.skipped + other.skipped,
        )


def _jsonable(value: Any) -> Any:
    """date 는 JSON 으로 못 나가므로 문자열로 바꾼다."""
    return value.isoformat() if isinstance(value, date) else value


def job_content_hash(row: dict[str, Any]) -> str:
    """공고 내용 해시. 이 값이 같으면 UPDATE 를 건너뛴다."""
    return content_hash({name: _jsonable(row.get(name)) for name in CONTENT_FIELDS})


def upsert_companies(session: Session, companies: pl.DataFrame) -> dict[str, int]:
    """회사를 적재하고 {name_normalized: id} 매핑을 돌려준다.

    입력 프레임은 name_normalized 로 이미 중복이 접혀 있어야 한다.
    한 배치에 같은 키가 두 번 들어오면 Postgres 가 DO UPDATE 를 거부한다.
    """
    if companies.is_empty():
        return {}

    rows = [
        {
            "name": row["company_name"],
            "name_normalized": row["company_name_normalized"],
            "industry_name": row["industry_name"],
            "size_category": row["size_category"],
            "homepage": row["homepage"],
        }
        for row in companies.to_dicts()
    ]

    stmt = insert(Company).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_companies_name_normalized",
        set_={
            "name": stmt.excluded.name,
            "industry_name": stmt.excluded.industry_name,
            "size_category": stmt.excluded.size_category,
            "homepage": stmt.excluded.homepage,
            "updated_at": func.now(),
        },
    )
    session.execute(stmt)

    keys = [row["name_normalized"] for row in rows]
    found = session.execute(
        select(Company.name_normalized, Company.id).where(Company.name_normalized.in_(keys))
    ).all()
    return {name: company_id for name, company_id in found}


def _job_row(row: dict[str, Any], company_ids: dict[str, int]) -> dict[str, Any]:
    """프레임 한 행을 jobs 테이블 컬럼으로 옮긴다."""
    payload = {name: row.get(name) for name in CONTENT_FIELDS}
    # Polars 안에서는 문자열로 들고 다녔다. JSONB 컬럼에 넣기 전에 되돌린다.
    payload["sections"] = json.loads(row["sections"]) if row.get("sections") else None
    payload["parse_flags"] = json.loads(row["parse_flags"]) if row.get("parse_flags") else None
    payload["source"] = row["source"]
    payload["source_id"] = row["source_id"]
    payload["company_id"] = company_ids.get(row["company_name_normalized"])
    payload["content_hash"] = job_content_hash(row)
    return payload


def upsert_jobs(
    session: Session, jobs: pl.DataFrame, company_ids: dict[str, int]
) -> tuple[int, int, int]:
    """공고를 적재한다. (신규, 갱신, 건너뜀) 을 돌려준다."""
    if jobs.is_empty():
        return 0, 0, 0

    rows = [_job_row(row, company_ids) for row in jobs.to_dicts()]
    updatable = [name for name in CONTENT_FIELDS] + ["company_id", "content_hash"]

    stmt = insert(Job).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_jobs_source_id",
        set_={name: getattr(stmt.excluded, name) for name in updatable}
        | {"updated_at": func.now()},
        # 내용이 그대로면 아무것도 하지 않는다
        where=Job.content_hash.is_distinct_from(stmt.excluded.content_hash),
    )
    # xmax 는 Postgres 내부 컬럼이다. INSERT 된 행은 0, UPDATE 된 행은 0이 아니다.
    # WHERE 에 걸려 건너뛴 행은 아예 반환되지 않으므로 세 가지가 구분된다.
    results: list[bool] = list(
        session.execute(stmt.returning(literal_column("(xmax = 0)"))).scalars().all()
    )

    inserted = sum(1 for was_insert in results if was_insert)
    updated = len(results) - inserted
    return inserted, updated, len(rows) - len(results)


def load_normalized(session: Session, jobs: pl.DataFrame, companies: pl.DataFrame) -> LoadResult:
    """회사 -> 공고 순으로 적재한다. 배치로 끊어 커밋 부담을 낮춘다."""
    company_ids = upsert_companies(session, companies)
    total = LoadResult(companies=len(company_ids))

    for start in range(0, jobs.height, BATCH_SIZE):
        chunk = jobs.slice(start, BATCH_SIZE)
        inserted, updated, skipped = upsert_jobs(session, chunk, company_ids)
        total = total + LoadResult(inserted=inserted, updated=updated, skipped=skipped)
    return total
