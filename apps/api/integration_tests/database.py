from dataclasses import dataclass
import os
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.pool import NullPool

from press_watch_api.config import DATABASE_URL_ENV


TEST_DATABASE_URL_ENV = "PRESSWATCH_TEST_DATABASE_URL"
TEST_DATABASE_PASSWORD_ENV = "PRESSWATCH_TEST_POSTGRES_PASSWORD"
TEST_DATABASE_DRIVER = "postgresql+psycopg"
TEST_DATABASE_HOST = "127.0.0.1"
TEST_DATABASE_PORT = 55_432
TEST_DATABASE_NAME = "presswatch_test"
TEST_DATABASE_USER = "presswatch_test"
TEST_DATABASE_MAJOR_VERSION = 17

_API_ROOT = Path(__file__).resolve().parents[1]
_ALLOWED_PUBLIC_TABLES = frozenset({"alembic_version", "press_releases"})


class UnsafeTestDatabaseError(RuntimeError):
    """テスト専用と確認できないDB接続を拒否する例外"""


@dataclass(frozen=True)
class TestDatabaseIdentity:
    """実接続先から取得したテストDBの識別情報

    Attributes:
        database: 接続中のDB名
        user: 接続中のDBユーザー名
        major_version: PostgreSQLのメジャーバージョン
    """

    database: str
    user: str
    major_version: int


def validate_test_database_url(database_url: str) -> URL:
    """DB変更前にテスト専用URLの構成要素を検証

    Args:
        database_url: 検証するテスト専用DB接続URL

    Returns:
        検証済みのSQLAlchemy URL

    Raises:
        UnsafeTestDatabaseError: テスト専用接続先と確認できない場合
    """

    try:
        url = make_url(database_url)
    except (ArgumentError, ValueError):
        raise UnsafeTestDatabaseError(
            "テスト専用DB接続URLの形式を確認できません。"
        ) from None

    checks = (
        (url.drivername == TEST_DATABASE_DRIVER, "driver"),
        (url.host == TEST_DATABASE_HOST, "host"),
        (url.port == TEST_DATABASE_PORT, "port"),
        (url.database == TEST_DATABASE_NAME, "database"),
        (url.username == TEST_DATABASE_USER, "user"),
        (bool(url.password), "password"),
        (not url.query, "query"),
    )
    for is_safe, field_name in checks:
        if not is_safe:
            raise UnsafeTestDatabaseError(
                f"テスト専用DB接続URLの{field_name}が許可条件と一致しません。"
            )

    return url


def prepare_test_database(database_url: str | None = None) -> Engine:
    """安全確認後にAlembic headを適用したテストDB Engineを生成

    Args:
        database_url: テスト専用DB接続URL。未指定時は専用環境変数から取得

    Returns:
        Alembic head適用済みのテストDB Engine

    Raises:
        UnsafeTestDatabaseError: 接続先をテスト専用DBと確認できない場合
    """

    raw_database_url = database_url or os.getenv(TEST_DATABASE_URL_ENV)
    if not raw_database_url:
        raise UnsafeTestDatabaseError(
            f"{TEST_DATABASE_URL_ENV}が設定されていません。"
        )

    url = validate_test_database_url(raw_database_url)
    _verify_database_target(url)
    _run_migrations_from_base(url)

    engine = _create_test_engine(url)
    try:
        _read_verified_identity(engine)
    except UnsafeTestDatabaseError:
        engine.dispose()
        raise
    except SQLAlchemyError:
        engine.dispose()
        raise UnsafeTestDatabaseError(
            "migration後のテスト専用DBを確認できません。"
        ) from None

    return engine


def get_current_migration_head() -> str:
    """リポジトリ内のAlembic migration graphから現在のheadを取得

    Returns:
        現在のAlembic head revision

    Raises:
        RuntimeError: migration graphにheadが存在しない場合
    """

    current_head = ScriptDirectory.from_config(
        _build_alembic_config()
    ).get_current_head()
    if current_head is None:
        raise RuntimeError("Alembic migration graphにheadが存在しません。")

    return current_head


def _create_test_engine(url: URL) -> Engine:
    return create_engine(url, poolclass=NullPool)


def _verify_database_target(url: URL) -> None:
    engine = _create_test_engine(url)
    try:
        _read_verified_identity(engine)
    except SQLAlchemyError:
        raise UnsafeTestDatabaseError(
            "テスト専用DBの安全確認に失敗しました。"
        ) from None
    finally:
        engine.dispose()


def _read_verified_identity(engine: Engine) -> TestDatabaseIdentity:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "select current_database(), current_user, "
                "current_setting('server_version_num')"
            )
        ).one()
        identity = TestDatabaseIdentity(
            database=row[0],
            user=row[1],
            major_version=int(row[2]) // 10_000,
        )
        _assert_expected_identity(identity)

        public_tables = frozenset(
            inspect(connection).get_table_names(schema="public")
        )
        unexpected_tables = public_tables - _ALLOWED_PUBLIC_TABLES
        if unexpected_tables:
            raise UnsafeTestDatabaseError(
                "テスト専用DBにmigration管理外のテーブルが存在します。"
            )

    return identity


def _assert_expected_identity(identity: TestDatabaseIdentity) -> None:
    checks = (
        (identity.database == TEST_DATABASE_NAME, "database"),
        (identity.user == TEST_DATABASE_USER, "user"),
        (
            identity.major_version == TEST_DATABASE_MAJOR_VERSION,
            "PostgreSQL major version",
        ),
    )
    for is_safe, field_name in checks:
        if not is_safe:
            raise UnsafeTestDatabaseError(
                f"実接続先の{field_name}が許可条件と一致しません。"
            )


def _run_migrations_from_base(url: URL) -> None:
    alembic_config = _build_alembic_config()

    rendered_url = url.render_as_string(hide_password=False)
    with patch.dict(os.environ, {DATABASE_URL_ENV: rendered_url}):
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")


def _build_alembic_config() -> Config:
    alembic_config = Config(str(_API_ROOT / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(_API_ROOT / "migrations"),
    )
    alembic_config.set_main_option(
        "prepend_sys_path",
        str(_API_ROOT / "src"),
    )
    return alembic_config
