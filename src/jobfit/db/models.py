"""ORM 모델 정의. Alembic이 이 모듈을 import해서 스키마를 감지한다."""

from jobfit.db.base import Base

__all__ = ["Base"]

# Phase 1에서 RawJobPosting, Company, Job, Skill ... 추가
