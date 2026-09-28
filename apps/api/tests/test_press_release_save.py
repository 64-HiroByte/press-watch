from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, patch

from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease
from press_watch_api.schemas.press_release import PressReleaseCreate
from press_watch_api.services import fixed_category_classification as classification
from press_watch_api.services.press_release_save import (
    list_known_release_urls_for_crawl,
    save_press_releases,
    to_press_release_create,
    to_press_release_creates,
)
from api_test_constants import (
    ENV_PRESS_RELEASE_URL_1 as SOURCE_URL_1,
    ENV_PRESS_RELEASE_URL_2 as SOURCE_URL_2,
    ENV_PRESS_RELEASE_URL_3 as SOURCE_URL_3,
)


@dataclass(frozen=True)
class ScraperPressReleaseStub:
    """scraper の PressRelease と同じ属性を持つテスト用データ"""

    title: str
    published_at: date
    url: str
    source_categories: tuple[str, ...]


class PressReleaseCreateSchemaTest(unittest.TestCase):
    """報道発表保存DTOのテスト"""

    def test_press_release_create_requires_timezone_aware_fetched_at(
        self,
    ) -> None:
        """取得日時にtimezone naiveな値を許可しないこと"""

        with self.assertRaises(ValidationError):
            PressReleaseCreate(
                title="報道発表",
                source_url=SOURCE_URL_1,
                published_at=date(2026, 5, 26),
                source_categories=["総合政策"],
                fetched_at=datetime(2026, 5, 26, 10, 0),
            )

    def test_press_release_create_normalizes_fetched_at_to_utc(self) -> None:
        """取得日時をUTCへ正規化すること"""

        fetched_at = datetime(
            2026,
            5,
            26,
            19,
            0,
            tzinfo=timezone(timedelta(hours=9)),
        )

        dto = PressReleaseCreate(
            title="報道発表",
            source_url=SOURCE_URL_1,
            published_at=date(2026, 5, 26),
            source_categories=["総合政策"],
            fetched_at=fetched_at,
        )

        self.assertEqual(dto.fetched_at, datetime(2026, 5, 26, 10, 0, tzinfo=UTC))

    def test_press_release_create_rejects_empty_required_text(self) -> None:
        """必須文字列に空文字列を許可しないこと"""

        with self.assertRaises(ValidationError):
            PressReleaseCreate(
                title="  ",
                source_url=SOURCE_URL_1,
                published_at=date(2026, 5, 26),
                source_categories=["総合政策"],
                fetched_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
            )

    def test_press_release_create_rejects_invalid_source_url(self) -> None:
        """保存対象のASCII HTTP(S) URI以外を許可しないこと"""

        cases = (
            ("", "must not be empty"),
            ("ftp://example.com/press/1", "unsupported_scheme"),
            (
                "https://user:password@example.com/press/1",
                "credentials_not_allowed",
            ),
            (
                "https://example.com/press/invalid path.html",
                "unsafe_character",
            ),
            (
                "https://example.com/press/invalid<path.html",
                "unsafe_character",
            ),
            (
                "https://example.com/press/invalid\\path.html",
                "unsafe_character",
            ),
            (
                "https://example.com/press/invalid%ZZpath.html",
                "invalid_percent_escape",
            ),
            (
                "https://example.com/press/日本語.html",
                "non_ascii_character",
            ),
            (
                "https://exa%20mple.com/press/1",
                "invalid_host_or_port",
            ),
            (
                "https://example.com:invalid/press/1",
                "invalid_host_or_port",
            ),
        )

        for source_url, reason in cases:
            with self.subTest(source_url=source_url):
                with self.assertRaises(ValidationError) as raised:
                    PressReleaseCreate(
                        title="報道発表",
                        source_url=source_url,
                        published_at=date(2026, 5, 26),
                        source_categories=["総合政策"],
                        fetched_at=datetime(
                            2026,
                            5,
                            26,
                            10,
                            0,
                            tzinfo=UTC,
                        ),
                    )
                self.assertIn(reason, str(raised.exception))

    def test_press_release_create_accepts_percent_encoded_unicode_url(
        self,
    ) -> None:
        """percent encode済みの日本語パスをURIとして許可すること"""

        source_url = (
            "https://example.com/press/"
            "%E6%97%A5%E6%9C%AC%E8%AA%9E.html"
        )

        dto = PressReleaseCreate(
            title="報道発表",
            source_url=source_url,
            published_at=date(2026, 5, 26),
            source_categories=["総合政策"],
            fetched_at=datetime(2026, 5, 26, 10, 0, tzinfo=UTC),
        )

        self.assertEqual(dto.source_url, source_url)


class PressReleaseSaveServiceTest(unittest.TestCase):
    """scraper 取得結果からDB保存DTOへの変換テスト"""

    def setUp(self) -> None:
        # このクラスは原本保存の契約を確認し、ルール照合は専用テストへ分ける。
        self.rule_loader = self.enterContext(patch.object(
            classification, "load_fixed_category_rules", return_value=((51, "大気"),),
        ))

    def test_to_press_release_create_maps_scraper_fields_to_save_dto(
        self,
    ) -> None:
        """scraper の url を保存DTOの source_url に写すこと"""

        release = _scraped_release(
            source_categories=("総合政策", "自然環境"),
        )
        fetched_at = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

        dto = to_press_release_create(release, fetched_at=fetched_at)

        self.assertEqual(dto.title, release.title)
        self.assertEqual(dto.source_url, release.url)
        self.assertEqual(dto.published_at, release.published_at)
        self.assertEqual(dto.source_categories, ["総合政策", "自然環境"])
        self.assertEqual(dto.fetched_at, fetched_at)

    def test_to_press_release_create_normalizes_empty_categories_to_none(
        self,
    ) -> None:
        """空の取得元カテゴリをNoneへ正規化すること"""

        release = _scraped_release(source_categories=())
        fetched_at = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

        dto = to_press_release_create(release, fetched_at=fetched_at)

        self.assertIsNone(dto.source_categories)

    def test_to_press_release_create_uses_utc_now_when_fetched_at_is_omitted(
        self,
    ) -> None:
        """取得日時の省略時にtimezone awareなUTC日時を補うこと"""

        release = _scraped_release(source_categories=("総合政策",))

        dto = to_press_release_create(release)

        self.assertIsNotNone(dto.fetched_at.tzinfo)
        self.assertEqual(dto.fetched_at.utcoffset(), timedelta(0))

    def test_to_press_release_creates_uses_same_fetched_at_for_batch(
        self,
    ) -> None:
        """一括変換では同じ取得日時を各DTOへ設定すること"""

        releases = [
            _scraped_release(
                title="報道発表1",
                url=SOURCE_URL_1,
            ),
            _scraped_release(
                title="報道発表2",
                url=SOURCE_URL_2,
            ),
        ]
        fetched_at = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

        dtos = to_press_release_creates(releases, fetched_at=fetched_at)

        self.assertEqual(
            [dto.source_url for dto in dtos],
            [release.url for release in releases],
        )
        self.assertEqual([dto.fetched_at for dto in dtos], [fetched_at, fetched_at])

    def test_save_press_releases_saves_each_scraped_release(
        self,
    ) -> None:
        """複数のscraper取得結果をDTO経由でrepositoryへ渡すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        saved_first = _saved_press_release(SOURCE_URL_1)
        saved_second = _saved_press_release(SOURCE_URL_2)
        session.scalars.return_value = (saved_first, saved_second)
        releases = [
            _scraped_release(
                title="報道発表1",
                url=SOURCE_URL_1,
                source_categories=("総合政策",),
            ),
            _scraped_release(
                title="報道発表2",
                url=SOURCE_URL_2,
                source_categories=(),
            ),
        ]
        fetched_at = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

        result = save_press_releases(
            session,
            releases,
            fetched_at=fetched_at,
        )
        press_releases = result.saved_press_releases

        self.assertEqual(len(press_releases), 2)
        self.assertIs(press_releases[0], saved_first)
        self.assertIs(press_releases[1], saved_second)
        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 0)
        session.scalar.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        parameters = statement.compile(dialect=postgresql.dialect()).params
        for index, release in enumerate(releases):
            expected_values = {
                "title": release.title,
                "source_url": release.url,
                "published_at": release.published_at,
                "source_categories": list(release.source_categories) or None,
                "fetched_at": fetched_at,
            }
            for column_name, expected_value in expected_values.items():
                self.assertTrue(
                    parameters[f"{column_name}_m{index}"] == expected_value,
                    f"INSERTの{index}行目の{column_name}が変換結果と一致しません。",
                )

    def test_save_press_releases_skips_existing_source_url(
        self,
    ) -> None:
        """既存source_urlの報道発表を保存せずskip件数へ数えること"""

        session = Mock(spec=Session)
        session.scalar.side_effect = [None, 1, None]
        saved_first = _saved_press_release(SOURCE_URL_1)
        saved_third = _saved_press_release(SOURCE_URL_3)
        session.scalars.return_value = (saved_first, saved_third)
        releases = [
            _scraped_release(
                title="報道発表1",
                url=SOURCE_URL_1,
            ),
            _scraped_release(
                title="報道発表2",
                url=SOURCE_URL_2,
            ),
            _scraped_release(
                title="報道発表3",
                url=SOURCE_URL_3,
            ),
        ]
        fetched_at = datetime(2026, 5, 26, 10, 0, tzinfo=UTC)

        result = save_press_releases(
            session,
            releases,
            fetched_at=fetched_at,
        )

        self.assertTrue(
            [
                press_release.source_url
                for press_release in result.saved_press_releases
            ] == [SOURCE_URL_1, SOURCE_URL_3],
            "保存結果のsource_url順が一致しません。",
        )
        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 1)
        session.scalar.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.scalars.assert_called_once()

    def test_save_press_releases_bulk_saves_mixed_duplicates_in_input_order(
        self,
    ) -> None:
        """混在する重複を一括保存し保存結果を入力順へ戻すこと"""

        session = Mock(spec=Session)
        session.scalar.side_effect = [None, 1, 1, None]
        saved_first = _saved_press_release(SOURCE_URL_1)
        saved_later = _saved_press_release(SOURCE_URL_3)
        session.scalars.return_value = (saved_later, saved_first)
        releases = [
            _scraped_release(
                title="入力内で最初の報道発表",
                url=SOURCE_URL_1,
            ),
            _scraped_release(
                title="DB既存相当の報道発表",
                url=SOURCE_URL_2,
            ),
            _scraped_release(
                title="入力内で重複する後続の報道発表",
                url=SOURCE_URL_1,
            ),
            _scraped_release(
                title="後続の新規報道発表",
                url=SOURCE_URL_3,
            ),
        ]

        result = save_press_releases(session, releases)

        session.scalar.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        parameters = statement.compile(dialect=postgresql.dialect()).params
        self.assertEqual(len(parameters), 15)
        self.assertTrue(
            releases[0].title in parameters.values(),
            "入力内で最初のDTOが保存候補に含まれていません。",
        )
        self.assertTrue(
            releases[2].title not in parameters.values(),
            "入力内で重複する後続DTOが保存候補に含まれています。",
        )
        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 2)
        self.assertEqual(
            result.saved_press_releases,
            (saved_first, saved_later),
        )
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_save_press_releases_splits_1001_candidates_into_two_batches(
        self,
    ) -> None:
        """1,001候補を1,000件と1件に分け全体の入力順を維持すること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        releases = [
            _scraped_release(
                title=f"報道発表{index}",
                url=f"https://example.test/press/{index}",
            )
            for index in range(1_001)
        ]
        saved_press_releases = [
            _saved_press_release(release.url)
            for release in releases
        ]
        session.scalars.side_effect = (
            tuple(reversed(saved_press_releases[:1_000])),
            tuple(reversed(saved_press_releases[1_000:])),
        )

        result = save_press_releases(session, releases)

        self.assertEqual(session.scalars.call_count, 2)
        parameter_counts = [
            len(
                called.args[0].compile(
                    dialect=postgresql.dialect(),
                ).params
            )
            for called in session.scalars.call_args_list
        ]
        self.assertEqual(parameter_counts, [5_000, 5])
        self.assertTrue(
            all(
                actual is expected
                for actual, expected in zip(
                    result.saved_press_releases,
                    saved_press_releases,
                    strict=True,
                )
            ),
            "保存結果が入力順と一致しません。",
        )
        self.assertEqual(result.saved_count, 1_001)
        self.assertEqual(result.skipped_count, 0)
        session.scalar.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_save_press_releases_does_not_execute_sql_for_empty_input(
        self,
    ) -> None:
        """空入力では保存SQLを実行しないこと"""

        session = Mock(spec=Session)

        result = save_press_releases(session, [])

        self.rule_loader.assert_not_called()
        self.assertEqual(result.saved_press_releases, ())
        self.assertEqual(result.saved_count, 0)
        self.assertEqual(result.skipped_count, 0)
        session.scalar.assert_not_called()
        session.scalars.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_save_press_releases_validates_all_input_before_saving(
        self,
    ) -> None:
        """後続入力のDTO検証失敗時に先行入力もDBへ渡さないこと"""

        session = Mock(spec=Session)
        releases = [
            _scraped_release(url=SOURCE_URL_1),
            _scraped_release(url="invalid-source-url"),
        ]

        with self.assertRaises(ValidationError):
            save_press_releases(session, releases)

        self.rule_loader.assert_not_called()
        session.scalar.assert_not_called()
        session.scalars.assert_not_called()
        session.add.assert_not_called()
        session.flush.assert_not_called()

    def test_save_press_releases_uses_same_omitted_fetched_at_for_all_dtos(
        self,
    ) -> None:
        """省略した取得日時を同じ呼び出し内の全DTOで一致させること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
        session.scalars.return_value = (
            _saved_press_release(SOURCE_URL_1),
            _saved_press_release(SOURCE_URL_2),
        )
        releases = [
            _scraped_release(url=SOURCE_URL_1),
            _scraped_release(url=SOURCE_URL_2),
        ]

        save_press_releases(session, releases)

        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        parameters = statement.compile(dialect=postgresql.dialect()).params
        fetched_at_values = [
            value
            for name, value in parameters.items()
            if name.startswith("fetched_at_")
        ]
        self.assertEqual(len(fetched_at_values), 2)
        self.assertEqual(len(set(fetched_at_values)), 1)
        self.assertIsNotNone(fetched_at_values[0].tzinfo)
        self.assertEqual(fetched_at_values[0].utcoffset(), timedelta(0))

    def test_save_press_releases_leaves_transaction_control_to_caller(
        self,
    ) -> None:
        """serviceでもトランザクションの確定や取消を呼び出し元へ任せること"""

        session = Mock(spec=Session)
        session.scalars.return_value = ()
        release = _scraped_release()

        save_press_releases(session, [release])

        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_list_known_release_urls_for_crawl_uses_latest_three_months(
        self,
    ) -> None:
        """最新公開月を含む直近3か月のsource_urlを返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = date(2026, 7, 25)
        session.scalars.return_value = [SOURCE_URL_1, SOURCE_URL_2]

        source_urls = list_known_release_urls_for_crawl(
            session,
            month_count=3,
        )

        self.assertEqual(source_urls, (SOURCE_URL_1, SOURCE_URL_2))
        session.scalar.assert_called_once()
        session.scalars.assert_called_once()
        statement = session.scalars.call_args.args[0]
        self.assertIn(date(2026, 5, 1), statement.compile().params.values())

    def test_list_known_release_urls_for_crawl_handles_year_boundary(
        self,
    ) -> None:
        """最新公開月から3か月分を年またぎで計算すること"""

        session = Mock(spec=Session)
        session.scalar.return_value = date(2026, 1, 15)
        session.scalars.return_value = [SOURCE_URL_1]

        list_known_release_urls_for_crawl(session, month_count=3)

        statement = session.scalars.call_args.args[0]
        self.assertIn(date(2025, 11, 1), statement.compile().params.values())

    def test_list_known_release_urls_for_crawl_returns_empty_for_empty_db(
        self,
    ) -> None:
        """保存済み報道発表がない場合は空のタプルを返すこと"""

        session = Mock(spec=Session)
        session.scalar.return_value = None

        source_urls = list_known_release_urls_for_crawl(
            session,
            month_count=3,
        )

        self.assertEqual(source_urls, ())
        session.scalars.assert_not_called()

    def test_list_known_release_urls_for_crawl_rejects_non_positive_month_count(
        self,
    ) -> None:
        """既知URLの取得月数に0以下を許可しないこと"""

        session = Mock(spec=Session)

        with self.assertRaisesRegex(ValueError, "month_count must be positive"):
            list_known_release_urls_for_crawl(session, month_count=0)

        session.scalar.assert_not_called()

    def test_list_known_release_urls_for_crawl_rejects_date_range_overflow(
        self,
    ) -> None:
        """Pythonの日付範囲を超える月数を拒否すること"""

        session = Mock(spec=Session)
        session.scalar.return_value = date(1, 1, 1)

        with self.assertRaisesRegex(
            ValueError,
            "month_count exceeds the supported date range",
        ):
            list_known_release_urls_for_crawl(session, month_count=2)

        session.scalars.assert_not_called()


class PressReleaseClassificationSaveTest(unittest.TestCase):
    def test_rejects_unseeded_categories_for_new_release(self) -> None:
        session = Mock(spec=Session)
        session.scalars.return_value = (_saved_press_release(SOURCE_URL_1),)
        with (
            patch("press_watch_api.repositories.fixed_category.list_fixed_categories", return_value=()),
            patch("press_watch_api.repositories.fixed_category.list_fixed_category_keywords", return_value=()),
            self.assertRaisesRegex(classification.FixedCategoryClassificationError, "fixed category definitions are not ready"),
        ):
            save_press_releases(session, [_scraped_release(url=SOURCE_URL_1)])
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_classifies_only_returned_new_models_by_actual_ids(self) -> None:
        session = Mock(spec=Session)
        first = _saved_press_release(SOURCE_URL_1, title="大気汚染と土壌", release_id=1009)
        later = _saved_press_release(SOURCE_URL_3, title="土壌", release_id=2017)
        session.scalars.return_value = (later, first)
        releases = [
            _scraped_release(url=SOURCE_URL_1, title=first.title),
            _scraped_release(url=SOURCE_URL_2, title="大気と土壌"),
            _scraped_release(url=SOURCE_URL_1, title="後続の重複入力"),
            _scraped_release(url=SOURCE_URL_3, title=later.title),
        ]
        rules = classification.prepare_fixed_category_rules(((51, "大気"), (51, "大気汚染"), (92, "土壌")))
        with patch.object(classification, "load_fixed_category_rules", return_value=rules) as load:
            result = save_press_releases(session, releases)
        load.assert_called_once_with(session)
        session.execute.assert_called_once()
        params = session.execute.call_args.args[0].compile(dialect=postgresql.dialect()).params
        self.assertEqual({
            (params[f"press_release_id_m{i}"], params[f"fixed_category_id_m{i}"])
            for i in range(len(params) // 2)
        }, {(1009, 51), (1009, 92), (2017, 92)})
        self.assertEqual(result.saved_press_releases, (first, later))
        self.assertEqual((result.saved_count, result.skipped_count), (2, 2))
        session.commit.assert_not_called()
        session.rollback.assert_not_called()

    def test_loads_rules_once_when_first_new_row_is_in_second_batch(self) -> None:
        session = Mock(spec=Session)
        releases = [_scraped_release(url=f"https://example.test/{i}", title="大気") for i in range(2_001)]
        session.scalars.side_effect = (
            (),
            (_saved_press_release(releases[1_000].url, title="大気", release_id=1009),),
            (_saved_press_release(releases[2_000].url, title="大気", release_id=2017),),
        )

        def load_rules(_session):
            self.assertEqual(session.scalars.call_count, 2)
            return ((51, "大気"),)

        with patch.object(classification, "load_fixed_category_rules", side_effect=load_rules) as load:
            result = save_press_releases(session, releases)
        load.assert_called_once_with(session)
        self.assertEqual(session.execute.call_count, 2)
        self.assertEqual((result.saved_count, result.skipped_count), (2, 1_999))

    def test_empty_and_all_skipped_inputs_never_load_rules_or_insert_classifications(self) -> None:
        for releases in ([], [_scraped_release(), _scraped_release()]):
            with self.subTest(count=len(releases)):
                session = Mock(spec=Session)
                session.scalars.return_value = ()
                with patch.object(classification, "load_fixed_category_rules") as load:
                    result = save_press_releases(session, releases)
                load.assert_not_called()
                session.execute.assert_not_called()
                self.assertEqual((result.saved_count, result.skipped_count), (0, len(releases)))
                self.assertEqual(session.scalars.call_count, bool(releases))

    def test_does_not_classify_source_categories_or_modify_original_title(self) -> None:
        session = Mock(spec=Session)
        saved = _saved_press_release(SOURCE_URL_1, title="お知らせ ＡＢＣ")
        session.scalars.return_value = (saved,)
        with patch.object(classification, "load_fixed_category_rules", return_value=((51, "大気"),)):
            save_press_releases(session, [_scraped_release(title=saved.title, source_categories=("大気",))])
        session.execute.assert_not_called()
        self.assertEqual(saved.title, "お知らせ ＡＢＣ")

    def test_classification_failure_propagates_without_committing(self) -> None:
        session = Mock(spec=Session)
        session.scalars.return_value = (_saved_press_release(SOURCE_URL_1),)
        error = RuntimeError("fixed classification failure")
        with (
            patch.object(classification, "load_fixed_category_rules", return_value=((51, "大気"),)),
            patch.object(classification, "classify_title", side_effect=error),
            self.assertRaises(RuntimeError) as caught,
        ):
            save_press_releases(session, [_scraped_release()])
        self.assertIs(caught.exception, error)
        session.execute.assert_not_called()
        session.commit.assert_not_called()
        session.rollback.assert_not_called()


def _scraped_release(
    title: str = "報道発表",
    published_at: date = date(2026, 5, 26),
    url: str = SOURCE_URL_1,
    source_categories: tuple[str, ...] = ("総合政策",),
) -> ScraperPressReleaseStub:
    """scraper 取得結果のテスト用データを生成

    Args:
        title: 報道発表タイトル
        published_at: 報道発表日
        url: 報道発表詳細ページURL
        source_categories: 取得元カテゴリ

    Returns:
        scraper 取得結果と同じ属性を持つテスト用データ
    """

    return ScraperPressReleaseStub(
        title=title,
        published_at=published_at,
        url=url,
        source_categories=source_categories,
    )


def _saved_press_release(source_url: str, *, title: str = "報道発表", release_id: int = 1009) -> Mock:
    """一括INSERTのRETURNING結果に相当するモデルMockを生成"""

    press_release = Mock(spec=PressRelease)
    press_release.source_url = source_url
    press_release.title = title
    press_release.id = release_id
    return press_release


if __name__ == "__main__":
    unittest.main()
