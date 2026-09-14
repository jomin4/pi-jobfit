"""DB 엔진 / 세션 / ORM Base. 모든 DB 접근의 출발점."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from jobfit.config import settings

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # 죽은 커넥션을 먼저 걸러낸다 (컨테이너 재시작 대비)
    pool_size=5,
    max_overflow=10,
    echo=False,  # True로 바꾸면 실행되는 SQL이 전부 찍힌다 — 디버깅에 유용
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,  # commit 후에도 객체 속성을 계속 읽을 수 있게
)


class Base(DeclarativeBase):
    """모든 ORM 모델의 부모 클래스."""


def get_session() -> Generator[Session, None, None]:
    """FastAPI 의존성 주입용. 요청 하나당 세션 하나를 열고 반드시 닫는다.

    commit은 호출하는 쪽에서 명시적으로 한다 (어디서 쓰기가 일어나는지 코드에 드러나도록).
    """
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
