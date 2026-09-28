from dataclasses import dataclass
from threading import Lock

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from press_watch_api.config import load_settings


@dataclass(frozen=True)
class _DatabaseResources:
    """プロセス内で共有するSQLAlchemyの初期化結果

    Attributes:
        engine: PostgreSQL接続を管理するEngine
        session_factory: DB Sessionを生成するファクトリ
    """

    engine: Engine
    session_factory: sessionmaker[Session]


class _DatabaseResourceProvider:
    """SQLAlchemyリソースの遅延初期化と再利用を管理"""

    def __init__(self) -> None:
        """未初期化状態のDBリソース管理オブジェクトを生成"""

        self._resources: _DatabaseResources | None = None
        self._lock = Lock()

    def get_resources(self) -> _DatabaseResources:
        """初期化済みのDBリソースを取得

        Returns:
            プロセス内で共有するSQLAlchemyの初期化結果
        """

        with self._lock:
            if self._resources is None:
                self._resources = self._build_resources()

            return self._resources

    @staticmethod
    def _build_resources() -> _DatabaseResources:
        """DB設定からEngineとSessionファクトリを生成

        Returns:
            新しく生成したSQLAlchemyの初期化結果
        """

        settings = load_settings()
        engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
        return _DatabaseResources(
            engine=engine,
            session_factory=sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=engine,
            ),
        )


_database_resource_provider = _DatabaseResourceProvider()


def get_engine() -> Engine:
    """遅延初期化した共有Engineを取得

    Returns:
        PostgreSQL接続を管理するEngine
    """

    return _database_resource_provider.get_resources().engine


def get_session_factory() -> sessionmaker[Session]:
    """遅延初期化した共有Sessionファクトリを取得

    Returns:
        DB Sessionを生成するファクトリ
    """

    return _database_resource_provider.get_resources().session_factory
