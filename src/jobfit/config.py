"""애플리케이션 설정. 모든 환경변수 접근은 이 모듈을 통해서만 한다."""

from functools import lru_cache

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env에 아직 안 쓰는 키가 있어도 무시
    )

    # App
    app_env: str = "local"
    log_level: str = "INFO"

    # Postgres — 필드명이 대소문자 구분 없이 환경변수와 자동 매핑된다
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "jobfit"
    postgres_user: str = "jobfit"
    postgres_password: str = "jobfit_dev"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        """SQLAlchemy 접속 문자열. psycopg3 드라이버를 명시한다."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """설정 객체는 프로세스당 한 번만 생성한다(.env 파일 I/O를 반복하지 않기 위해)."""
    return Settings()


settings = get_settings()
