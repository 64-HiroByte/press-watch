from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from sqlalchemy.orm import Session

from press_watch_api.models.press_release import PressRelease as PressReleaseModel
from press_watch_api.repositories.press_release import (
    create_press_release,
    get_latest_press_release_published_at,
    has_press_release_with_source_url,
    list_press_release_source_urls_published_from,
)
from press_watch_api.schemas.press_release import PressReleaseCreate


@dataclass(frozen=True)
class PressReleaseSaveResult:
    """報道発表の保存結果"""

    saved_press_releases: tuple[PressReleaseModel, ...]
    skipped_count: int

    @property
    def saved_count(self) -> int:
        """保存件数"""

        return len(self.saved_press_releases)


class ScrapedPressRelease(Protocol):
    """scraper 取得結果として保存変換に必要な属性"""

    title: str
    published_at: date
    url: str
    source_categories: Collection[str]


def to_press_release_create(
    release: ScrapedPressRelease,
    fetched_at: datetime | None = None,
) -> PressReleaseCreate:
    """scraper 取得結果をDB保存用DTOへ変換

    Args:
        release: scraper が取得した報道発表
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        DB新規保存用の報道発表DTO
    """

    return PressReleaseCreate(
        title=release.title,
        source_url=release.url,
        published_at=release.published_at,
        source_categories=_source_categories_or_none(
            release.source_categories,
        ),
        fetched_at=fetched_at or datetime.now(UTC),
    )


def to_press_release_creates(
    releases: Iterable[ScrapedPressRelease],
    fetched_at: datetime | None = None,
) -> list[PressReleaseCreate]:
    """複数の scraper 取得結果をDB保存用DTOへ変換

    Args:
        releases: scraper が取得した報道発表の反復可能オブジェクト
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        DB新規保存用の報道発表DTOリスト
    """

    resolved_fetched_at = fetched_at or datetime.now(UTC)
    return [
        to_press_release_create(
            release,
            fetched_at=resolved_fetched_at,
        )
        for release in releases
    ]


def save_press_releases(
    session: Session,
    releases: Iterable[ScrapedPressRelease],
    fetched_at: datetime | None = None,
) -> PressReleaseSaveResult:
    """scraper 取得結果をDTO経由でrepositoryへ保存依頼

    repository と同じく commit / rollback は呼び出さず、
    呼び出し元のトランザクションに参加する。

    Args:
        session: 保存に使うSQLAlchemyセッション
        releases: scraper が取得した報道発表の反復可能オブジェクト
        fetched_at: 環境省ページからデータを取得した日時

    Returns:
        保存済みモデルと保存件数、重複skip件数を含む保存結果
    """

    create_dtos = to_press_release_creates(
        releases,
        fetched_at=fetched_at,
    )
    saved_press_releases: list[PressReleaseModel] = []
    skipped_count = 0

    for create_dto in create_dtos:
        if has_press_release_with_source_url(
            session,
            create_dto.source_url,
        ):
            skipped_count += 1
            continue

        saved_press_releases.append(
            create_press_release(
                session,
                create_dto,
            )
        )

    return PressReleaseSaveResult(
        saved_press_releases=tuple(saved_press_releases),
        skipped_count=skipped_count,
    )


def list_known_release_urls_for_crawl(
    session: Session,
    *,
    month_count: int,
) -> tuple[str, ...]:
    """差分取得の既知URLとして直近の保存済みURLを取得

    Args:
        session: 取得に使うSQLAlchemyセッション
        month_count: 最新公開月を含めて取得する月数

    Returns:
        scraper 側へ取得済みとして渡す `source_url` のタプル

    Raises:
        ValueError: 月数が0以下または日付範囲を超える場合
    """

    if month_count <= 0:
        raise ValueError("month_count must be positive")

    latest_published_at = get_latest_press_release_published_at(session)
    if latest_published_at is None:
        return ()

    published_from = _month_window_start(
        latest_published_at,
        month_count,
    )
    return list_press_release_source_urls_published_from(
        session,
        published_from,
    )


def _month_window_start(
    latest_published_at: date,
    month_count: int,
) -> date:
    """最新公開月を含む月範囲の開始日を算出

    Args:
        latest_published_at: 保存済み報道発表の最新公開日
        month_count: 最新公開月を含める月数

    Returns:
        月範囲の最初の月の1日

    Raises:
        ValueError: 算出結果がPythonの日付範囲より前になる場合
    """

    month_index = (
        latest_published_at.year * 12
        + latest_published_at.month
        - month_count
    )
    if month_index < 12:
        raise ValueError("month_count exceeds the supported date range")
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)


def _source_categories_or_none(
    source_categories: Collection[str],
) -> list[str] | None:
    """保存方針に合わせて空カテゴリをNoneへ正規化

    Args:
        source_categories: scraper が取得した取得元カテゴリ

    Returns:
        カテゴリが1件以上ある場合は文字列リスト、空の場合はNone
    """

    if not source_categories:
        return None
    return list(source_categories)
