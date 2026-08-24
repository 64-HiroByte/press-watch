from collections.abc import Iterator

from sqlalchemy.orm import Session

from press_watch_api.db import get_session_factory


def get_db_session() -> Iterator[Session]:
    """HTTPリクエストで使用するDB Sessionを生成

    Yields:
        path operationへ渡すSQLAlchemy Session
    """

    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
