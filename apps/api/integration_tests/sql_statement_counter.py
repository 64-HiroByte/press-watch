from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from sqlalchemy import event
from sqlalchemy.engine import Engine


@dataclass
class SqlStatementCounts:
    """保存区間で実行されたSQL種別ごとの件数"""

    select: int = 0
    insert: int = 0
    press_release_insert: int = 0
    classification_insert: int = 0

    @property
    def total(self) -> int:
        """SELECTとINSERTの合計実行回数"""

        return self.select + self.insert

    def to_json_dict(self) -> dict[str, int]:
        """入力データを含まない実行回数の辞書へ変換"""

        return {
            "select": self.select,
            "insert": self.insert,
            "total": self.total,
        }


@contextmanager
def count_save_sql_statements(
    engine: Engine,
) -> Iterator[SqlStatementCounts]:
    """対象区間のSELECTとINSERTだけを数えlistenerを確実に解除"""

    counts = SqlStatementCounts()

    def count_statement(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: object,
    ) -> None:
        operation = statement.lstrip().partition(" ")[0].upper()
        if operation == "SELECT":
            counts.select += 1
        elif operation == "INSERT":
            counts.insert += 1
            compiled = getattr(_context, "compiled", None)
            table = getattr(getattr(compiled, "statement", None), "table", None)
            table_name = getattr(table, "name", None)
            if table_name == "press_releases":
                counts.press_release_insert += 1
            elif table_name == "press_release_fixed_categories":
                counts.classification_insert += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
