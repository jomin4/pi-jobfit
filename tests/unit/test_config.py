"""설정 모듈 단위 테스트."""

from jobfit.config import Settings


def test_database_url이_psycopg3_드라이버를_사용한다() -> None:
    settings = Settings(
        postgres_user="u",
        postgres_password="p",
        postgres_host="h",
        postgres_port=1234,
        postgres_db="d",
    )

    assert settings.database_url == "postgresql+psycopg://u:p@h:1234/d"


def test_포트는_문자열로_줘도_정수로_변환된다() -> None:
    settings = Settings(postgres_port="5433")  # type: ignore[arg-type]

    assert settings.postgres_port == 5433
