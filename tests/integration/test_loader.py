"""적재 통합 테스트. 실제 Postgres 가 필요하다."""

from collections.abc import Iterator
from typing import Any

import polars as pl
import pytest
from sqlalchemy import delete, func, select

from jobfit.db.base import SessionLocal
from jobfit.db.models import Company, Job
from jobfit.processing.loader import job_content_hash, load_normalized
from jobfit.processing.normalize import normalize_details

pytestmark = pytest.mark.integration

SOURCE = "test-loader"


def _payload(no: str, title: str = "백엔드 개발자", corp: str = "(주)테스트") -> dict[str, Any]:
    return {
        "wantedAuthNo": no,
        "regDt": "2026-09-01",
        "corpInfo": {"corpNm": corp, "indTpCdNm": "정보서비스업", "busiSize": "중소기업"},
        "wantedInfo": {
            "wantedTitle": title,
            "jobCont": "Python 기반 API 개발",
            "sal": "연 4000~5000만원",
            "salTpCd": "Y",
            "enterTpNm": "경력 3년 이상",
            "enterTpCd": "E",
            "receiptCloseDt": "2026-10-01",
            "minEdubgIcd": "05",
            "empTpCd": "10",
            "jobsNm": "백엔드",
            "regionCd": "11000",
            "workRegion": "서울특별시",
        },
    }


def _clear() -> None:
    with SessionLocal() as session:
        session.execute(delete(Job).where(Job.source == SOURCE))
        # 이 테스트가 만든 회사만 지운다
        session.execute(delete(Company).where(Company.name_normalized == "테스트"))
        session.commit()


@pytest.fixture
def clean_db() -> Iterator[None]:
    _clear()
    yield
    _clear()


def _load(payloads: list[dict[str, Any]]) -> Any:
    result = normalize_details(SOURCE, payloads)
    with SessionLocal() as session:
        outcome = load_normalized(session, result.jobs, result.companies)
        session.commit()
    return outcome


def _count_jobs() -> int:
    with SessionLocal() as session:
        return session.execute(
            select(func.count()).select_from(Job).where(Job.source == SOURCE)
        ).scalar_one()


def test_처음_적재하면_전부_신규다(clean_db: None) -> None:
    outcome = _load([_payload(f"T-{i:03d}") for i in range(5)])

    assert (outcome.inserted, outcome.updated, outcome.skipped) == (5, 0, 0)
    assert outcome.companies == 1
    assert _count_jobs() == 5


def test_내용이_같으면_UPDATE_조차_하지_않는다(clean_db: None) -> None:
    payloads = [_payload(f"T-{i:03d}") for i in range(5)]
    _load(payloads)

    outcome = _load(payloads)

    assert (outcome.inserted, outcome.updated, outcome.skipped) == (0, 0, 5)
    assert _count_jobs() == 5


def test_내용이_바뀐_공고만_갱신된다(clean_db: None) -> None:
    payloads = [_payload(f"T-{i:03d}") for i in range(5)]
    _load(payloads)
    payloads[0]["wantedInfo"]["wantedTitle"] = "수정된 제목"

    outcome = _load(payloads)

    assert (outcome.inserted, outcome.updated, outcome.skipped) == (0, 1, 4)
    with SessionLocal() as session:
        title = session.execute(
            select(Job.title).where(Job.source == SOURCE, Job.source_id == "T-000")
        ).scalar_one()
    assert title == "수정된 제목"


def test_공고가_회사에_연결된다(clean_db: None) -> None:
    _load([_payload("T-000"), _payload("T-001")])

    with SessionLocal() as session:
        rows = session.execute(
            select(Job.company_id, Company.name_normalized)
            .join(Company, Job.company_id == Company.id)
            .where(Job.source == SOURCE)
        ).all()

    assert len(rows) == 2
    assert {name for _, name in rows} == {"테스트"}
    assert len({company_id for company_id, _ in rows}) == 1  # 같은 회사 = 같은 id


def test_전문검색_컬럼이_자동으로_채워진다(clean_db: None) -> None:
    """search_tsv 는 GENERATED 컬럼이라 적재만 해도 채워져야 한다."""
    _load([_payload("T-000", title="백엔드 개발자 (Python)")])

    with SessionLocal() as session:
        hits = session.execute(
            select(func.count())
            .select_from(Job)
            .where(
                Job.source == SOURCE, Job.search_tsv.op("@@")(func.to_tsquery("simple", "python"))
            )
        ).scalar_one()

    assert hits == 1


def test_company_id는_해시에_들어가지_않는다() -> None:
    """DB 상태 때문에 내용이 바뀐 것처럼 보이면 안 된다."""
    base = {"title": "a", "description": "b"}

    assert job_content_hash(base) == job_content_hash({**base, "company_id": 999})


def test_빈_프레임을_넣어도_터지지_않는다(clean_db: None) -> None:
    empty = normalize_details(SOURCE, [])

    with SessionLocal() as session:
        outcome = load_normalized(session, empty.jobs, empty.companies)
        session.commit()

    assert outcome == type(outcome)()


def test_배치_경계를_넘어도_숫자가_맞는다(clean_db: None) -> None:
    """BATCH_SIZE(500) 보다 많은 행에서 카운터가 어긋나지 않는지."""
    payloads = [_payload(f"T-{i:04d}") for i in range(600)]

    outcome = _load(payloads)

    assert outcome.inserted == 600
    assert _count_jobs() == 600


def test_같은_회사의_다른_표기도_한_행으로_모인다(clean_db: None) -> None:
    _load([_payload("T-000", corp="(주)테스트"), _payload("T-001", corp="테스트 주식회사")])

    with SessionLocal() as session:
        count = session.execute(
            select(func.count()).select_from(Company).where(Company.name_normalized == "테스트")
        ).scalar_one()

    assert count == 1


def test_슬라이스된_프레임도_정상_적재된다(clean_db: None) -> None:
    result = normalize_details(SOURCE, [_payload(f"T-{i:03d}") for i in range(10)])
    half: pl.DataFrame = result.jobs.slice(0, 5)

    with SessionLocal() as session:
        outcome = load_normalized(session, half, result.companies)
        session.commit()

    assert outcome.inserted == 5
    assert _count_jobs() == 5
