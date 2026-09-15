"""ORM 모델 정의. Alembic이 이 모듈을 import해서 스키마를 감지한다."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobfit.db.base import Base


class RawJobPosting(Base):
    """수집 원문 — append-only. 절대 UPDATE 하지 않는다.

    파싱 로직이 바뀌면 이 테이블에서 하위 레이어를 전부 다시 만든다.
    """

    __tablename__ = "raw_job_postings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint: Mapped[str | None] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        # 같은 공고의 같은 내용은 한 번만 저장한다 (수집 멱등성의 핵심)
        UniqueConstraint("source", "source_id", "content_hash", name="uq_raw_source_hash"),
        # 미처리분만 오래된 순으로 꺼내는 부분 인덱스 — 처리 완료분은 인덱스에 안 들어간다
        Index(
            "ix_raw_unprocessed",
            "fetched_at",
            postgresql_where=text("processed_at IS NULL"),
        ),
    )


class IngestionRun(Base):
    """수집 실행 1회의 기록. 무엇이 언제 몇 건 들어왔고 몇 번 호출했는지."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    # server_default 를 쓰는 이유: default= 는 파이썬(SQLAlchemy)이 채우므로
    # psql·Airflow·raw SQL 로 INSERT 하면 NOT NULL 위반이 난다. DB가 채우게 한다.
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default=text("'running'")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 사람인 API 일 500회 제한(ADR-001) 추적용
    api_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    fetched_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    new_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    error_detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    __table_args__ = (Index("ix_ingestion_runs_source_started", "source", "started_at"),)


class Company(Base):
    """채용 공고를 올린 회사. 여러 소스의 같은 회사를 하나로 모은다."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 공백·법인격(주식회사/(주)) 제거한 형태. 소스가 달라도 같은 회사로 묶는 키
    name_normalized: Mapped[str] = mapped_column(String(200), nullable=False)
    # 사업자등록번호. 사람인 응답엔 없고 고용24엔 있다 → nullable
    biz_no: Mapped[str | None] = mapped_column(String(20))
    industry_code: Mapped[str | None] = mapped_column(String(20))
    industry_name: Mapped[str | None] = mapped_column(String(100))
    size_category: Mapped[str | None] = mapped_column(String(20))
    homepage: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="company")

    __table_args__ = (
        UniqueConstraint("name_normalized", name="uq_companies_name_normalized"),
        # 사업자번호는 있을 때만 유일해야 한다 (NULL 여러 개는 허용)
        Index(
            "uq_companies_biz_no",
            "biz_no",
            unique=True,
            postgresql_where=text("biz_no IS NOT NULL"),
        ),
    )


class Job(Base):
    """정규화된 채용공고. 매칭·임베딩·RAG의 기준 테이블."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # --- 출처 식별 ---
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))

    # --- 본문 ---
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 소스가 제공하는 구분(직무내용/자격요건/우대사항)을 그대로 담는다
    sections: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # --- 분류 ---
    job_category: Mapped[str | None] = mapped_column(String(50))
    employment_type: Mapped[str | None] = mapped_column(String(20))

    # --- 조건 ---
    exp_min: Mapped[int | None] = mapped_column(SmallInteger)
    exp_max: Mapped[int | None] = mapped_column(SmallInteger)
    education: Mapped[str | None] = mapped_column(String(20))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_raw: Mapped[str | None] = mapped_column(String(200))
    region_code: Mapped[str | None] = mapped_column(String(20))
    region_name: Mapped[str | None] = mapped_column(String(100))

    # --- 기간 / 상태 ---
    posted_at: Mapped[date | None] = mapped_column(Date)
    deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="open", server_default=text("'open'")
    )
    url: Mapped[str | None] = mapped_column(String(500))

    # --- 운영 ---
    parse_flags: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company | None"] = relationship(back_populates="jobs")

    # 제목+본문을 합쳐 DB가 자동 생성하는 전문검색 컬럼.
    # 한국어 형태소 분석기가 없으므로 'simple' 설정 사용(공백/문장부호 분리).
    # 영문 기술용어 검색에는 충분하고, 한국어 부분일치는 pg_trgm 으로 보완한다.
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(description, ''))",
            persisted=True,
        ),
    )

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_jobs_source_id"),
        CheckConstraint("exp_min IS NULL OR exp_min >= 0", name="ck_jobs_exp_min_nonneg"),
        CheckConstraint(
            "exp_max IS NULL OR exp_min IS NULL OR exp_max >= exp_min",
            name="ck_jobs_exp_range",
        ),
        CheckConstraint("status IN ('open', 'closed', 'expired')", name="ck_jobs_status"),
        Index("ix_jobs_status_deadline", "status", "deadline"),
        Index("ix_jobs_region_category", "region_code", "job_category"),
        Index("ix_jobs_exp", "exp_min", "exp_max"),
        Index("ix_jobs_search_tsv", "search_tsv", postgresql_using="gin"),
        Index("ix_jobs_company", "company_id"),
    )
