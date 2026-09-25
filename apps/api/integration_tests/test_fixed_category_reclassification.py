from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime
import io
import json
import unittest
from unittest.mock import Mock, patch

from sqlalchemy import delete, event, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from integration_tests.database import prepare_test_database
from press_watch_api.commands.reclassify_fixed_categories import main
from press_watch_api.models.fixed_category import FixedCategory, FixedCategoryKeyword, PressReleaseFixedCategory
from press_watch_api.models.press_release import PressRelease
from press_watch_api.repositories import fixed_category as category_repository
from press_watch_api.services import fixed_category_classification as classification
from press_watch_api.services import fixed_category_reclassification as service
from press_watch_api.services.fixed_category_seed import load_fixed_category_seed, seed_fixed_categories


_DATA_MODELS = (PressReleaseFixedCategory, FixedCategoryKeyword, FixedCategory, PressRelease)
_RESULT_TABLE = "press_release_fixed_categories"


class FixedCategoryReclassificationIntegrationTest(unittest.TestCase):
    """外側のtransactionを使わず、CLIの確定・取消を別接続から確認"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = prepare_test_database()
        cls.addClassCleanup(cls.engine.dispose)

    def setUp(self) -> None:
        self.sessions: list[Session] = []
        self.addCleanup(self._clear_test_data)
        self.data = load_fixed_category_seed()

    def _clear_test_data(self) -> None:
        for session in self.sessions:
            session.close()
        self.sessions.clear()
        with self.engine.begin() as connection:
            for model in _DATA_MODELS:
                connection.execute(delete(model))

    def _seed(self) -> dict[str, int]:
        with Session(self.engine) as session:
            session.add_all([
                FixedCategory(id=(index + 1) * 101, slug=item.slug, name=item.name, display_order=item.display_order)
                for index, item in enumerate(self.data.categories)
            ])
            session.flush()
            seed_fixed_categories(session, self.data)
            ids = {item.slug: item.id for item in session.scalars(select(FixedCategory))}
            session.commit()
        return ids

    def _create_releases(self, titles: Sequence[str], *, old_category_id: int | None = None) -> tuple[int, ...]:
        # 非連番・0・負のIDで、初回に正のIDだけへ限定しないことも確認する。
        release_ids = tuple(index * 3 - 6 for index in range(len(titles)))
        with Session(self.engine) as session:
            session.add_all([
                PressRelease(
                    id=release_id, title=title, source_url=f"https://example.test/reclassification/{release_id}",
                    published_at=date(2026, 9, 1), source_categories=["大気"],
                    fetched_at=datetime(2026, 9, 2, 1, tzinfo=UTC),
                    created_at=datetime(2026, 9, 2, 2, tzinfo=UTC),
                    updated_at=datetime(2026, 9, 2, 3, tzinfo=UTC),
                )
                for release_id, title in zip(release_ids, titles, strict=True)
            ])
            session.flush()
            if old_category_id is not None:
                category_repository.create_press_release_fixed_categories(
                    session, [(release_id, old_category_id) for release_id in release_ids],
                )
            session.commit()
        return release_ids

    def _session(self) -> Session:
        session = Session(self.engine)
        self.sessions.append(session)
        return session

    def _run_cli(self) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        code = main([], session_factory=self._session, stdout=stdout, stderr=stderr)
        return code, stdout.getvalue(), stderr.getvalue()

    def _snapshot(self) -> dict[str, tuple[tuple[object, ...], ...]]:
        with self.engine.connect() as connection:
            return {
                model.__tablename__: tuple(tuple(row) for row in connection.execute(
                    select(model.__table__).order_by(*model.__table__.primary_key.columns)
                ))
                for model in _DATA_MODELS
            }

    def _assert_failure_preserves(self, before: dict, result: tuple[int, str, str]) -> None:
        code, stdout, stderr = result
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("operation=reclassify commit_succeeded=false", stderr)
        for forbidden in ("PRIVATE_", "Traceback", "INSERT INTO", "DELETE FROM", "psycopg"):
            self.assertNotIn(forbidden, stderr)
        self.assertEqual(self._snapshot(), before)

    def test_replaces_old_and_missing_results_without_changing_originals_or_definitions(self) -> None:
        ids = self._seed()
        release_ids = self._create_releases(
            ("ＰＣＢと大気汚染", "新しいお知らせ", "水道水と公共用水域", "精度管理調査", "土壌の調査"),
            old_category_id=ids["noise"],
        )
        with Session(self.engine) as session:
            category_repository.delete_press_release_fixed_categories(session, [release_ids[-1]])
            session.commit()
        before = self._snapshot()
        delete_checks = 0

        def verify_uncommitted_delete(_conn, _cursor, statement, _parameters, _context, _many):
            nonlocal delete_checks
            if statement.lstrip().upper().startswith("DELETE"):
                delete_checks += 1
                self.assertEqual(self._snapshot(), before)

        event.listen(self.engine, "after_cursor_execute", verify_uncommitted_delete)
        try:
            code, stdout, stderr = self._run_cli()
        finally:
            event.remove(self.engine, "after_cursor_execute", verify_uncommitted_delete)
        self.assertEqual((code, stderr, delete_checks), (0, "", 1))
        self.assertEqual(json.loads(stdout), {"processed_count": 5, "matched_count": 4, "classification_count": 6})
        after = self._snapshot()
        expected = {
            (release_ids[0], ids["air"]), (release_ids[0], ids["other"]),
            (release_ids[2], ids["tap_water"]), (release_ids[2], ids["environmental_water"]),
            (release_ids[3], ids["common"]), (release_ids[4], ids["soil"]),
        }
        self.assertEqual(set(after[_RESULT_TABLE]), expected)
        for table in ("press_releases", "fixed_categories", "fixed_category_keywords"):
            self.assertEqual(after[table], before[table])
        self.assertEqual(self._run_cli(), (code, stdout, stderr))
        self.assertEqual(self._snapshot(), after)

    def test_repository_deletion_preserves_unselected_ids_and_empty_deletion_does_nothing(self) -> None:
        ids = self._seed()
        release_ids = self._create_releases(("大気", "土壌", "お知らせ"), old_category_id=ids["noise"])
        with Session(self.engine) as session:
            category_repository.delete_press_release_fixed_categories(session, [release_ids[0]])
            session.commit()
        before = self._snapshot()
        self.assertEqual(set(before[_RESULT_TABLE]), {(release_id, ids["noise"]) for release_id in release_ids[1:]})
        with _count_sql(self.engine) as counts, Session(self.engine) as session:
            category_repository.delete_press_release_fixed_categories(session, [])
            session.commit()
        self.assertEqual(counts, Counter())
        self.assertEqual(self._snapshot(), before)

    def test_empty_database_validates_rules_without_writing(self) -> None:
        self._seed()
        before = self._snapshot()
        with _count_sql(self.engine) as counts:
            code, stdout, stderr = self._run_cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"processed_count": 0, "matched_count": 0, "classification_count": 0})
        self.assertEqual(counts, Counter({("SELECT", "fixed_categories"): 1, ("SELECT", "fixed_category_keywords"): 1, ("SELECT", "press_releases"): 1}))
        self.assertEqual(self._snapshot(), before)

    def test_unseeded_rules_fail_before_reading_releases_even_when_empty(self) -> None:
        for titles in ((), ("大気",)):
            with self.subTest(count=len(titles)):
                self._create_releases(titles)
                before = self._snapshot()
                with _count_sql(self.engine) as counts:
                    result = self._run_cli()
                self._assert_failure_preserves(before, result)
                self.assertEqual(counts, Counter({("SELECT", "fixed_categories"): 1, ("SELECT", "fixed_category_keywords"): 1}))

    def test_csv_failure_does_not_issue_sql_or_change_results(self) -> None:
        ids = self._seed()
        self._create_releases(("大気",), old_category_id=ids["noise"])
        before = self._snapshot()
        with patch.object(classification, "load_fixed_category_seed", side_effect=OSError("PRIVATE_CSV_PATH")), _count_sql(self.engine) as counts:
            result = self._run_cli()
        self._assert_failure_preserves(before, result)
        self.assertEqual(counts, Counter())

    def test_definition_mismatches_preserve_existing_results(self) -> None:
        for variant in ("category", "missing_keyword", "extra_keyword"):
            with self.subTest(variant=variant):
                ids = self._seed()
                self._create_releases(("大気",), old_category_id=ids["noise"])
                with Session(self.engine) as session:
                    if variant == "category":
                        session.execute(update(FixedCategory).where(FixedCategory.id == ids["air"]).values(name="不一致の表示名"))
                    elif variant == "missing_keyword":
                        session.execute(delete(FixedCategoryKeyword).where(FixedCategoryKeyword.fixed_category_id == ids["air"]))
                    else:
                        session.add(FixedCategoryKeyword(fixed_category_id=ids["air"], keyword="追加されたキーワード"))
                    session.commit()
                before = self._snapshot()
                with _count_sql(self.engine) as counts:
                    result = self._run_cli()
                self._assert_failure_preserves(before, result)
                self.assertEqual(counts, Counter({("SELECT", "fixed_categories"): 1, ("SELECT", "fixed_category_keywords"): 1}))
                self._clear_test_data()

    def test_batch_boundaries_and_repeat_execution_have_bounded_sql_counts(self) -> None:
        for count in (1000, 1001):
            with self.subTest(count=count):
                ids = self._seed()
                release_ids = self._create_releases(("大気",) * count, old_category_id=ids["noise"])
                for attempt in range(2):
                    with self.subTest(attempt=attempt), _count_sql(self.engine) as counts:
                        code, stdout, stderr = self._run_cli()
                    self.assertEqual((code, stderr), (0, ""))
                    self.assertEqual(json.loads(stdout), {"processed_count": count, "matched_count": count, "classification_count": count})
                    self.assertEqual(counts, Counter({
                        ("SELECT", "fixed_categories"): 1, ("SELECT", "fixed_category_keywords"): 1,
                        ("SELECT", "press_releases"): count // 1000 + 1,
                        ("DELETE", _RESULT_TABLE): (count + 999) // 1000,
                        ("INSERT", _RESULT_TABLE): (count + 999) // 1000,
                    }))
                    self.assertEqual(set(self._snapshot()[_RESULT_TABLE]), {(release_id, ids["air"]) for release_id in release_ids})
                self._clear_test_data()

    def test_multiple_matches_split_inserts_and_unmatched_results_are_removed(self) -> None:
        ids = self._seed()
        self._create_releases(("大気と土壌",) * 501 + ("新しいお知らせ",), old_category_id=ids["noise"])
        with _count_sql(self.engine) as counts:
            code, stdout, stderr = self._run_cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"processed_count": 502, "matched_count": 501, "classification_count": 1002})
        self.assertEqual(counts, Counter({
            ("SELECT", "fixed_categories"): 1, ("SELECT", "fixed_category_keywords"): 1,
            ("SELECT", "press_releases"): 1, ("DELETE", _RESULT_TABLE): 1, ("INSERT", _RESULT_TABLE): 2,
        }))
        self.assertEqual(len(self._snapshot()[_RESULT_TABLE]), 1002)

    def test_all_unmatched_releases_remove_old_results_without_inserts(self) -> None:
        ids = self._seed()
        self._create_releases(("新しいお知らせ",) * 3, old_category_id=ids["noise"])
        with _count_sql(self.engine) as counts:
            code, stdout, stderr = self._run_cli()
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout), {"processed_count": 3, "matched_count": 0, "classification_count": 0})
        self.assertEqual(counts[("INSERT", _RESULT_TABLE)], 0)
        self.assertEqual(counts[("DELETE", _RESULT_TABLE)], 1)
        self.assertEqual(self._snapshot()[_RESULT_TABLE], ())

    def test_foreign_key_failure_after_delete_and_first_insert_restores_old_results(self) -> None:
        ids = self._seed()
        self._create_releases(("大気と土壌",) * 501, old_category_id=ids["noise"])
        before = self._snapshot()
        insert_count = 0
        sqlstates: list[str | None] = []

        def record_database_error(context):
            sqlstates.append(getattr(context.original_exception, "sqlstate", None))

        def fail_second_insert(_conn, _cursor, statement, parameters, context, _many):
            nonlocal insert_count
            if statement.lstrip().upper().startswith("INSERT") and _table_name(context) == _RESULT_TABLE:
                insert_count += 1
                if insert_count == 2:
                    # 先行INSERTとDELETEの後に、実際の外部キー違反を起こす。
                    parameters = dict(parameters)
                    parameters["fixed_category_id_m0"] = -1
            return statement, parameters

        event.listen(self.engine, "before_cursor_execute", fail_second_insert, retval=True)
        event.listen(self.engine, "handle_error", record_database_error)
        try:
            result = self._run_cli()
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_second_insert)
            event.remove(self.engine, "handle_error", record_database_error)
        self.assertEqual(insert_count, 2)
        self.assertEqual(sqlstates, ["23503"])
        self._assert_failure_preserves(before, result)

    def test_later_read_delete_classification_failure_and_interruption_restore_all_results(self) -> None:
        ids = self._seed()
        self._create_releases(("大気",) * 1001, old_category_id=ids["noise"])
        before = self._snapshot()
        for operation, target, name, failure_at in (
            ("read", service.release_repository, "list_press_release_titles_after_id", 2),
            ("delete", service.category_repository, "delete_press_release_fixed_categories", 2),
            ("classify", classification, "classify_title", 1001),
            ("interrupt", classification, "classify_title", 1001),
        ):
            with self.subTest(operation=operation):
                original = getattr(target, name)
                calls = 0

                def fail_later(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == failure_at:
                        if operation == "interrupt":
                            raise KeyboardInterrupt()
                        raise RuntimeError("PRIVATE_LATER_FAILURE")
                    return original(*args, **kwargs)

                with patch.object(target, name, side_effect=fail_later), _count_sql(self.engine) as counts:
                    result = self._run_cli()
                self.assertEqual(calls, failure_at)
                self.assertEqual(counts[("INSERT", _RESULT_TABLE)], 1)
                self._assert_failure_preserves(before, result)
                if operation == "interrupt":
                    self.assertIn("reason=operation interrupted", result[2])

    def test_output_failure_leaves_committed_results_in_database(self) -> None:
        ids = self._seed()
        release_ids = self._create_releases(("大気",), old_category_id=ids["noise"])
        output, errors = Mock(), io.StringIO()
        output.write.side_effect = OSError("PRIVATE_OUTPUT_DETAIL")
        self.assertEqual(main([], session_factory=self._session, stdout=output, stderr=errors), 1)
        self.assertIn("operation=output commit_succeeded=true", errors.getvalue())
        self.assertNotIn("PRIVATE_", errors.getvalue())
        self.assertEqual(self._snapshot()[_RESULT_TABLE], ((release_ids[0], ids["air"]),))


def _table_name(context: object) -> str | None:
    statement = getattr(getattr(context, "compiled", None), "statement", None)
    table = getattr(statement, "table", None)
    if table is None and getattr(statement, "is_select", False):
        sources = statement.get_final_froms()
        table = sources[0] if len(sources) == 1 else None
    return getattr(table, "name", None)


@contextmanager
def _count_sql(engine: Engine) -> Iterator[Counter[tuple[str, str | None]]]:
    """再分類区間のSQL種別・テーブルだけを数え、SQL本文や値は保存しない"""

    counts: Counter[tuple[str, str | None]] = Counter()

    def count_statement(_conn, _cursor, statement, _parameters, context, _many):
        operation = statement.lstrip().partition(" ")[0].upper()
        if operation in {"SELECT", "INSERT", "DELETE", "UPDATE"}:
            counts[(operation, _table_name(context))] += 1

    event.listen(engine, "before_cursor_execute", count_statement)
    try:
        yield counts
    finally:
        event.remove(engine, "before_cursor_execute", count_statement)
