from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from press_watch_api.commands.fetch_and_save_env_press import ScraperCliRelease
from press_watch_api.services.press_release_save import to_press_release_creates


_REQUIRED_TOP_LEVEL_KEYS = frozenset(
    {
        "archive_month_link_count",
        "archive_month_links",
        "count",
        "fetched_page_urls",
        "items",
        "source_url",
        "stop_reason",
    }
)
_REQUIRED_ITEM_KEYS = frozenset(
    {"published_at", "source_categories", "title", "url"}
)


class SnapshotValidationError(ValueError):
    """DB接続前のスナップショット入力検証に失敗した例外"""


@dataclass(frozen=True)
class ValidatedSnapshot:
    """DB接続前の検証を通過した報道発表スナップショット

    Attributes:
        releases: 保存serviceへ渡す報道発表
        fetched_at: すべての報道発表へ設定する取得完了時刻
        sha256: 入力ファイルのSHA-256
    """

    releases: tuple[ScraperCliRelease, ...]
    fetched_at: datetime
    sha256: str

    @property
    def fetched_count(self) -> int:
        """検証済み報道発表の件数"""

        return len(self.releases)


def load_validated_snapshot(
    snapshot_path: Path,
    *,
    expected_count: int,
    expected_sha256: str,
    fetched_at_text: str,
) -> ValidatedSnapshot:
    """JSONスナップショットを読み込み保存前の入力条件を検証

    Args:
        snapshot_path: 読み込むJSONスナップショットのパス
        expected_count: 期待する報道発表件数
        expected_sha256: 期待する入力ファイルのSHA-256
        fetched_at_text: 保存する取得完了時刻のISO 8601文字列

    Returns:
        保存serviceへ渡せる検証済みスナップショット
    """

    if not snapshot_path.is_file():
        raise SnapshotValidationError(
            "スナップショットファイルを読み取れません。"
        )
    try:
        snapshot_bytes = snapshot_path.read_bytes()
    except OSError:
        raise SnapshotValidationError(
            "スナップショットファイルを読み取れません。"
        ) from None

    actual_sha256 = hashlib.sha256(snapshot_bytes).hexdigest()
    if actual_sha256 != expected_sha256:
        raise SnapshotValidationError(
            "スナップショットのSHA-256が期待値と一致しません。"
        )

    try:
        payload = json.loads(snapshot_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SnapshotValidationError(
            "UTF-8のJSON objectとして読み取れません。"
        ) from None
    if type(payload) is not dict:
        raise SnapshotValidationError(
            "UTF-8のJSON objectとして読み取れません。"
        )
    if not _REQUIRED_TOP_LEVEL_KEYS.issubset(payload):
        raise SnapshotValidationError(
            "スナップショットの必須キーが不足しています。"
        )

    _validate_top_level_types(payload)
    items = payload["items"]
    if payload["count"] != expected_count or len(items) != expected_count:
        raise SnapshotValidationError(
            "スナップショットの件数が期待値と一致しません。"
        )

    fetched_at = _parse_fetched_at(fetched_at_text)
    releases = _parse_releases(items)
    try:
        create_dtos = to_press_release_creates(
            releases,
            fetched_at=fetched_at,
        )
    except (TypeError, ValueError, ValidationError):
        raise SnapshotValidationError(
            "報道発表を保存DTOへ変換できません。"
        ) from None

    normalized_urls = [create_dto.source_url for create_dto in create_dtos]
    if len(set(normalized_urls)) != len(normalized_urls):
        raise SnapshotValidationError(
            "スナップショットの詳細ページURLが重複しています。"
        )

    return ValidatedSnapshot(
        releases=releases,
        fetched_at=fetched_at,
        sha256=actual_sha256,
    )


def _validate_top_level_types(payload: dict[str, object]) -> None:
    """トップレベル値を暗黙変換せず検証

    Args:
        payload: 必須キーを確認済みのJSON object

    Raises:
        SnapshotValidationError: 値の型がスナップショット契約と異なる場合
    """

    values_are_valid = (
        type(payload["archive_month_link_count"]) is int
        and _is_archive_month_link_list(payload["archive_month_links"])
        and type(payload["count"]) is int
        and type(payload["items"]) is list
        and _is_string_list(payload["fetched_page_urls"])
        and type(payload["source_url"]) is str
        and (
            payload["stop_reason"] is None
            or type(payload["stop_reason"]) is str
        )
    )
    if not values_are_valid:
        raise SnapshotValidationError(
            "スナップショットの値の型が不正です。"
        )


def _parse_fetched_at(value: str) -> datetime:
    """取得完了時刻をtimezone awareなUTCへ変換

    Args:
        value: ISO 8601形式の取得完了時刻

    Returns:
        UTCへ正規化した取得完了時刻

    Raises:
        SnapshotValidationError: 日時をtimezone awareとして読めない場合
    """

    try:
        fetched_at = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise SnapshotValidationError(
            "取得完了時刻はtimezone awareである必要があります。"
        ) from None
    if fetched_at.tzinfo is None or fetched_at.utcoffset() is None:
        raise SnapshotValidationError(
            "取得完了時刻はtimezone awareである必要があります。"
        )
    return fetched_at.astimezone(UTC)


def _parse_releases(items: list[object]) -> tuple[ScraperCliRelease, ...]:
    """item配列を保存service用の報道発表へ変換

    Args:
        items: 件数を確認済みのJSON item配列

    Returns:
        型と必須キーを検証済みの報道発表

    Raises:
        SnapshotValidationError: itemのキー、型、日付が不正な場合
    """

    releases: list[ScraperCliRelease] = []
    for item in items:
        if type(item) is not dict:
            raise SnapshotValidationError(
                "スナップショットの値の型が不正です。"
            )
        if not _REQUIRED_ITEM_KEYS.issubset(item):
            raise SnapshotValidationError(
                "スナップショットの必須キーが不足しています。"
            )
        if not (
            type(item["title"]) is str
            and type(item["published_at"]) is str
            and type(item["url"]) is str
            and _is_string_list(item["source_categories"])
        ):
            raise SnapshotValidationError(
                "スナップショットの値の型が不正です。"
            )
        try:
            published_at = date.fromisoformat(item["published_at"])
        except ValueError:
            raise SnapshotValidationError(
                "報道発表を保存DTOへ変換できません。"
            ) from None
        releases.append(
            ScraperCliRelease(
                title=item["title"],
                published_at=published_at,
                url=item["url"],
                source_categories=tuple(item["source_categories"]),
            )
        )

    return tuple(releases)


def _is_string_list(value: object) -> bool:
    """値が文字列だけを含むlistか判定"""

    return type(value) is list and all(type(item) is str for item in value)


def _is_archive_month_link_list(value: object) -> bool:
    """値が月別アーカイブ情報だけを含むlistか判定"""

    if type(value) is not list:
        return False
    return all(
        type(item) is dict
        and {"year", "month", "url"}.issubset(item)
        and type(item["year"]) is int
        and type(item["month"]) is int
        and type(item["url"]) is str
        for item in value
    )
