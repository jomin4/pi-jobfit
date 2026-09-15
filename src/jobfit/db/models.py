"""ORM 모델 정의. Alembic이 이 모듈을 import해서 스키마를 감지한다."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

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
