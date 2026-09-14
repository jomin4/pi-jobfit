"""enable_extensions

Revision ID: 0001
Revises:
Create Date: 2026-09-14 15:07:48.522672

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector: 임베딩 벡터 타입과 유사도 인덱스 (Phase 3에서 사용)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # pg_trgm: 오타에 강한 부분 문자열 검색 (회사명 매칭 등)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
