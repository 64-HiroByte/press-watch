from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
import unittest
from unittest.mock import Mock, call

from pydantic import ValidationError
from sqlalchemy.orm import Session

from press_watch_api.schemas.press_release import PressReleaseCreate
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

        self.assertEqual(
            [press_release.source_url for press_release in press_releases],
            [release.url for release in releases],
        )
        self.assertEqual(
            [press_release.fetched_at for press_release in press_releases],
            [fetched_at, fetched_at],
        )
        self.assertEqual(press_releases[0].source_categories, ["総合政策"])
        self.assertIsNone(press_releases[1].source_categories)
        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 0)
        self.assertEqual(
            session.add.call_args_list,
            [
                call(press_releases[0]),
                call(press_releases[1]),
            ],
        )
        self.assertEqual(session.flush.call_count, 2)

    def test_save_press_releases_skips_existing_source_url(
        self,
    ) -> None:
        """既存source_urlの報道発表を保存せずskip件数へ数えること"""

        session = Mock(spec=Session)
        session.scalar.side_effect = [None, 1, None]
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

        self.assertEqual(
            [
                press_release.source_url
                for press_release in result.saved_press_releases
            ],
            [
                SOURCE_URL_1,
                SOURCE_URL_3,
            ],
        )
        self.assertEqual(result.saved_count, 2)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(session.scalar.call_count, 3)
        self.assertEqual(
            session.add.call_args_list,
            [
                call(result.saved_press_releases[0]),
                call(result.saved_press_releases[1]),
            ],
        )
        self.assertEqual(session.flush.call_count, 2)

    def test_save_press_releases_leaves_transaction_control_to_caller(
        self,
    ) -> None:
        """serviceでもトランザクションの確定や取消を呼び出し元へ任せること"""

        session = Mock(spec=Session)
        session.scalar.return_value = None
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


if __name__ == "__main__":
    unittest.main()
