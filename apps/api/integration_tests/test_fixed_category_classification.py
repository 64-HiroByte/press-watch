from datetime import UTC, date, datetime
import io
import json
import unittest
from unittest.mock import patch

from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import Session

from integration_tests.database import prepare_test_database
from integration_tests.sql_statement_counter import count_save_sql_statements
from press_watch_api.commands.fetch_and_save_env_press import (
    CollectedPressReleases,
    ScraperCliRelease,
    main,
)
from press_watch_api.models.fixed_category import (
    FixedCategory,
    FixedCategoryKeyword,
    PressReleaseFixedCategory,
)
from press_watch_api.models.press_release import PressRelease
from press_watch_api.repositories.press_release import create_press_release
from press_watch_api.services import fixed_category_classification as classification
from press_watch_api.services.fixed_category_seed import load_fixed_category_seed, seed_fixed_categories
from press_watch_api.services.press_release_save import save_press_releases, to_press_release_create


_DATA_MODELS = (PressReleaseFixedCategory, FixedCategoryKeyword, FixedCategory, PressRelease)
_FETCHED_AT = datetime(2026, 9, 25, 1, 0, tzinfo=UTC)


class FixedCategoryClassificationIntegrationTest(unittest.TestCase):
    """CLIのcommit・rollbackを専用DBへ反映し、別接続から保存結果を確認"""

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
        with self.engine.begin() as connection:
            for model in _DATA_MODELS:
                connection.execute(delete(model))

    def _seed(self) -> dict[str, int]:
        with Session(self.engine) as session:
            # CSV行番号・表示順と異なる実IDを分類結果へ使うことを確認する。
            session.add_all([
                FixedCategory(id=(index + 1) * 101, slug=item.slug, name=item.name, display_order=item.display_order)
                for index, item in enumerate(self.data.categories)
            ])
            session.flush()
            seed_fixed_categories(session, self.data)
            ids = {item.slug: item.id for item in session.scalars(select(FixedCategory))}
            session.commit()
        return ids

    def _session(self) -> Session:
        session = Session(self.engine)
        self.sessions.append(session)
        return session

    def _run_cli(self, releases: tuple[ScraperCliRelease, ...]) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        collected = CollectedPressReleases(
            source_url="https://example.test/press/", releases=releases,
            fetched_page_urls=(), stop_reason=None,
        )
        code = main(
            ["--url", collected.source_url], session_factory=self._session,
            collect_releases=lambda _args, _stderr, _known: collected,
            stdout=stdout, stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue()

    def _snapshot(self) -> dict[str, tuple[tuple[object, ...], ...]]:
        with self.engine.connect() as connection:
            return {
                model.__tablename__: tuple(
                    tuple(row) for row in connection.execute(
                        select(model.__table__).order_by(*model.__table__.primary_key.columns)
                    )
                )
                for model in _DATA_MODELS
            }

    def _create_existing(self, category_id: int | None = None) -> None:
        with Session(self.engine) as session:
            saved = create_press_release(session, to_press_release_create(
                _release(0, "既存の原本"), fetched_at=_FETCHED_AT,
            ))
            if category_id is not None:
                session.add(PressReleaseFixedCategory(press_release_id=saved.id, fixed_category_id=category_id))
            session.commit()

    def test_commits_only_new_classifications_and_preserves_original_values_and_duplicates(self) -> None:
        ids = self._seed()
        self._create_existing(ids["other"])
        before = self._snapshot()
        releases = (
            _release(1, "ＰＣＢと大気汚染"),
            _release(0, "土壌へ変更した既存URL"),
            _release(1, "後続の重複入力"),
            _release(2, "土壌の調査"),
            _release(3, "新しいお知らせ", source_categories=("大気",)),
        )
        with Session(self.engine) as session:
            result = save_press_releases(session, releases, fetched_at=_FETCHED_AT)
            self.assertEqual((result.saved_count, result.skipped_count), (3, 2))
            self.assertEqual([item.source_url for item in result.saved_press_releases], [releases[i].url for i in (0, 3, 4)])
            session.commit()

        after = self._snapshot()
        self.assertIn(before["press_releases"][0], after["press_releases"])
        self.assertIn(before["press_release_fixed_categories"][0], after["press_release_fixed_categories"])
        with Session(self.engine) as verification:
            rows = {item.source_url: item for item in verification.scalars(select(PressRelease))}
            pairs = set(verification.execute(select(
                PressReleaseFixedCategory.press_release_id, PressReleaseFixedCategory.fixed_category_id,
            )).tuples())
            self.assertEqual(pairs, {
                (rows[releases[0].url].id, ids["air"]),
                (rows[releases[0].url].id, ids["other"]),
                (rows[releases[3].url].id, ids["soil"]),
                before["press_release_fixed_categories"][0],
            })
            for release in (releases[0], releases[3], releases[4]):
                row = rows[release.url]
                self.assertEqual((row.title, row.source_categories, row.published_at, row.fetched_at), (
                    release.title, list(release.source_categories) or None, release.published_at, _FETCHED_AT,
                ))
        code, stdout, stderr = self._run_cli(releases)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual((json.loads(stdout)["saved_count"], json.loads(stdout)["skipped_count"]), (0, 5))
        self.assertEqual(self._snapshot(), after)

    def test_empty_and_all_skipped_succeed_without_seed(self) -> None:
        self._create_existing()
        before = self._snapshot()
        for releases in ((), (_release(0, "大気"),)):
            with self.subTest(count=len(releases)):
                with count_save_sql_statements(self.engine) as counts:
                    code, stdout, stderr = self._run_cli(releases)
                self.assertEqual((code, stderr), (0, ""))
                self.assertEqual(json.loads(stdout)["skipped_count"], len(releases))
                self.assertEqual((counts.select, counts.insert), (0, int(bool(releases))))
                self.assertEqual(self._snapshot(), before)

    def test_unseeded_new_save_rolls_back_original(self) -> None:
        before = self._snapshot()
        code, stdout, stderr = self._run_cli((_release(1, "大気"),))
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("reason=fixed category definitions are not ready", stderr)
        self.assertEqual(self._snapshot(), before)

    def test_mismatched_rules_reject_new_save_but_allow_all_skipped(self) -> None:
        ids = self._seed()
        self._create_existing(ids["other"])
        with self.engine.begin() as connection:
            connection.execute(update(FixedCategory).where(FixedCategory.id == ids["air"]).values(name="不一致の表示名"))
        before = self._snapshot()
        code, stdout, stderr = self._run_cli((_release(0, "大気"), _release(1, "大気")))
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("reason=fixed category definitions do not match bundled CSV", stderr)
        self.assertEqual(self._snapshot(), before)
        code, _, stderr = self._run_cli((_release(0, "大気"),))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(self._snapshot(), before)

    def test_missing_keyword_rolls_back_new_original(self) -> None:
        ids = self._seed()
        with self.engine.begin() as connection:
            connection.execute(delete(FixedCategoryKeyword).where(
                FixedCategoryKeyword.fixed_category_id == ids["air"], FixedCategoryKeyword.keyword == "大気",
            ))
        before = self._snapshot()
        self.assertEqual(self._run_cli((_release(1, "大気"),))[0], 1)
        self.assertEqual(self._snapshot(), before)

    def test_sql_counts_keep_original_batches_and_load_rules_once(self) -> None:
        self._seed()
        releases = tuple(_release(index, "大気") for index in range(1_001))
        with count_save_sql_statements(self.engine) as initial:
            self.assertEqual(self._run_cli(releases)[0], 0)
        self.assertEqual((initial.select, initial.press_release_insert, initial.classification_insert, initial.insert), (2, 2, 2, 4))
        with count_save_sql_statements(self.engine) as duplicate:
            self.assertEqual(self._run_cli(releases)[0], 0)
        self.assertEqual((duplicate.select, duplicate.press_release_insert, duplicate.classification_insert, duplicate.insert), (0, 2, 0, 2))

    def test_classification_rows_split_independently_of_original_batch(self) -> None:
        self._seed()
        with count_save_sql_statements(self.engine) as counts:
            code, stdout, stderr = self._run_cli(tuple(_release(index, "大気と土壌") for index in range(501)))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["saved_count"], 501)
        self.assertEqual((counts.select, counts.press_release_insert, counts.classification_insert), (2, 1, 2))
        self.assertEqual(len(self._snapshot()["press_release_fixed_categories"]), 1_002)

    def test_failure_after_first_classification_insert_rolls_back_both_tables(self) -> None:
        ids = self._seed()
        self._create_existing(ids["other"])
        before = self._snapshot()
        insert_count = 0
        classification_batch_sizes: list[int] = []

        def fail_second_classification(_conn, _cursor, statement, parameters, context, _many):
            nonlocal insert_count
            compiled = getattr(context, "compiled", None)
            table = getattr(getattr(compiled, "statement", None), "table", None)
            if statement.lstrip().upper().startswith("INSERT") and getattr(table, "name", None) == "press_release_fixed_categories":
                insert_count += 1
                classification_batch_sizes.append(len(compiled.params) // 2)
                if insert_count == 2:
                    # 先行INSERT後に実際の外部キー違反を起こし、DBエラー経路を通す。
                    parameters = dict(parameters)
                    parameters["fixed_category_id_m0"] = -1
            return statement, parameters

        event.listen(self.engine, "before_cursor_execute", fail_second_classification, retval=True)
        try:
            code, stdout, stderr = self._run_cli(tuple(_release(index + 1, "大気と土壌") for index in range(501)))
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_second_classification)
        self.assertEqual((code, stdout), (1, ""))
        self.assertEqual(stderr, (
            "error: target=https://example.test/press/ "
            "exception=IntegrityError reason=database operation failed\n"
        ))
        self.assertEqual(classification_batch_sizes, [1_000, 2])
        self.assertEqual(self._snapshot(), before)

    def test_second_original_insert_failure_rolls_back_prior_classifications(self) -> None:
        self._seed()
        before = self._snapshot()
        insert_count = 0

        def fail_second_original(_conn, _cursor, statement, _params, context, _many):
            nonlocal insert_count
            compiled = getattr(context, "compiled", None)
            table = getattr(getattr(compiled, "statement", None), "table", None)
            if statement.lstrip().upper().startswith("INSERT") and getattr(table, "name", None) == "press_releases":
                insert_count += 1
                if insert_count == 2:
                    raise RuntimeError("fixed original insert failure")

        event.listen(self.engine, "before_cursor_execute", fail_second_original)
        try:
            with count_save_sql_statements(self.engine) as counts:
                code, stdout, stderr = self._run_cli(tuple(_release(index, "大気") for index in range(1_001)))
        finally:
            event.remove(self.engine, "before_cursor_execute", fail_second_original)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("fixed original insert failure", stderr)
        self.assertEqual((insert_count, counts.classification_insert), (2, 1))
        self.assertEqual(self._snapshot(), before)

    def test_classifier_failure_in_later_batch_rolls_back_prior_originals_and_results(self) -> None:
        self._seed()
        before = self._snapshot()
        original_classifier = classification.classify_title

        def fail_later_title(title, rules):
            if title == "後半で失敗":
                raise RuntimeError("fixed classifier failure")
            return original_classifier(title, rules)

        releases = tuple(_release(index, "大気") for index in range(1_000)) + (_release(1_000, "後半で失敗"),)
        with patch.object(classification, "classify_title", side_effect=fail_later_title):
            code, stdout, stderr = self._run_cli(releases)
        self.assertEqual((code, stdout), (1, ""))
        self.assertIn("fixed classifier failure", stderr)
        self.assertEqual(self._snapshot(), before)


def _release(index: int, title: str, *, source_categories: tuple[str, ...] = ()) -> ScraperCliRelease:
    return ScraperCliRelease(
        title=title, published_at=date(2026, 9, 25),
        url=f"https://example.test/classification/{index}", source_categories=source_categories,
    )
