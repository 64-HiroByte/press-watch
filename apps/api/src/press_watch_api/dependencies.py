from collections.abc import Iterator
import sys

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from press_watch_api.db import get_session_factory
from press_watch_api.http_errors import (
    DatabaseLifecycleError,
    write_database_diagnostic,
)


def get_db_session() -> Iterator[Session]:
    """HTTPリクエストで使用するDB Sessionを生成

    Yields:
        path operationへ渡すSQLAlchemy Session
    """

    try:
        session_factory = get_session_factory()
        session = session_factory()
    except SQLAlchemyError:
        raise
    except Exception:
        raise DatabaseLifecycleError("initialization") from None
    try:
        yield session
    finally:
        # close中の例外ではなく、終了処理へ入る前の例外を優先する。
        has_pending_error = sys.exception() is not None
        try:
            session.close()
        except Exception as exc:
            if has_pending_error:
                write_database_diagnostic("database_cleanup_failed")
            elif isinstance(exc, SQLAlchemyError):
                raise
            else:
                raise DatabaseLifecycleError("cleanup") from None
