"""保存済み報道発表の固定カテゴリ再分類"""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from press_watch_api.repositories import fixed_category as category_repository
from press_watch_api.repositories import press_release as release_repository
from press_watch_api.services import (
    fixed_category_classification as classification,
)


_RECLASSIFICATION_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class PressReleaseReclassificationResult:
    """再分類した報道発表と分類結果の件数

    Attributes:
        processed_count: 判定した報道発表数
        matched_count: 1カテゴリ以上に一致した報道発表数
        classification_count: 置換後の報道発表・カテゴリの組数
    """

    processed_count: int
    matched_count: int
    classification_count: int


def reclassify_press_releases(
    session: Session,
) -> PressReleaseReclassificationResult:
    """保存済み全件の分類結果を現在のルールへ置換

    他の書込み処理と同時実行せず、呼出元で全件を一括commitする。
    例外時は呼出元で、先行バッチも含めて必ずrollbackする。

    Args:
        session: この処理のトランザクションを管理するSession

    Returns:
        全件処理後の件数。呼出元のcommit前であり、変更件数ではない

    Raises:
        classification.FixedCategoryClassificationError:
            CSV・DB定義が利用できない場合
    """

    rules = classification.load_fixed_category_rules(session)
    after_id: int | None = None
    processed_count = matched_count = classification_count = 0
    while True:
        batch = release_repository.list_press_release_titles_after_id(
            session,
            after_id=after_id,
            limit=_RECLASSIFICATION_BATCH_SIZE,
        )
        if not batch:
            break
        values: list[tuple[int, int]] = []
        batch_matched_count = 0
        for release_id, title in batch:
            category_ids = classification.classify_title(title, rules)
            batch_matched_count += bool(category_ids)
            values.extend(
                (release_id, category_id) for category_id in category_ids
            )
        # バッチ内の判定を終えてから、未一致の行も含めて古い結果を取り除く。
        category_repository.delete_press_release_fixed_categories(
            session,
            tuple(release_id for release_id, _title in batch),
        )
        category_repository.create_press_release_fixed_categories(
            session, values
        )
        processed_count += len(batch)
        matched_count += batch_matched_count
        classification_count += len(values)
        if len(batch) < _RECLASSIFICATION_BATCH_SIZE:
            break
        after_id = batch[-1][0]
    return PressReleaseReclassificationResult(
        processed_count, matched_count, classification_count
    )
