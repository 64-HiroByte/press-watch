from copy import deepcopy
from datetime import UTC, date, datetime
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "real_snapshot_valid.json"
_FIXTURE_SHA256 = (
    "e12206746b713a6aaa2ca845872b8a26678ba792759790be0459f6da38bd0b16"
)
_FETCHED_AT_TEXT = "2026-08-29T13:45:27.408274Z"


class RealSnapshotValidationTest(unittest.TestCase):
    """実データスナップショットの入力検証境界のテスト"""

    def setUp(self) -> None:
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

    def test_load_validated_snapshot_accepts_valid_fixture(self) -> None:
        """検証済みfixtureを保存serviceへ渡せる形で復元すること"""

        try:
            validation = importlib.import_module(
                "integration_tests.real_snapshot_validation"
            )
        except ModuleNotFoundError as exc:
            if exc.name != "integration_tests.real_snapshot_validation":
                raise
            self.fail(
                "実データスナップショットの入力検証経路が未実装です"
            )

        snapshot = validation.load_validated_snapshot(
            _FIXTURE_PATH,
            expected_count=2,
            expected_sha256=_FIXTURE_SHA256,
            fetched_at_text=_FETCHED_AT_TEXT,
        )

        self.assertEqual(snapshot.fetched_count, 2)
        self.assertEqual(snapshot.sha256, _FIXTURE_SHA256)
        self.assertEqual(
            snapshot.fetched_at,
            datetime(2026, 8, 29, 13, 45, 27, 408274, tzinfo=UTC),
        )
        self.assertEqual(snapshot.releases[0].title, "報道発表1")
        self.assertEqual(
            snapshot.releases[0].published_at,
            date(2026, 8, 29),
        )
        self.assertEqual(
            snapshot.releases[0].source_categories,
            ("総合政策",),
        )
        self.assertEqual(snapshot.releases[1].source_categories, ())

    def test_missing_or_non_regular_snapshot_is_rejected(self) -> None:
        """存在しないパスと通常ファイルでないパスを拒否すること"""

        missing_path = Path(self.temporary_directory.name) / "missing.json"
        directory_path = Path(self.temporary_directory.name)

        for snapshot_path in (missing_path, directory_path):
            with (
                self.subTest(snapshot_path=snapshot_path.name),
                self.assertRaisesRegex(
                    ValueError,
                    "スナップショットファイルを読み取れません。",
                ),
            ):
                self._load_snapshot(snapshot_path)

    def test_invalid_json_object_is_rejected(self) -> None:
        """UTF-8のJSON objectでない入力を拒否すること"""

        invalid_inputs = (
            b"\xff",
            b"{",
            b"[]",
        )

        for index, snapshot_bytes in enumerate(invalid_inputs):
            snapshot_path = self._write_bytes(
                f"invalid-{index}.json",
                snapshot_bytes,
            )
            with (
                self.subTest(index=index),
                self.assertRaisesRegex(
                    ValueError,
                    "UTF-8のJSON objectとして読み取れません。",
                ),
            ):
                self._load_snapshot(
                    snapshot_path,
                    expected_sha256=_sha256(snapshot_bytes),
                )

    def test_missing_required_keys_are_rejected(self) -> None:
        """トップレベルとitemの必須キー不足を拒否すること"""

        payloads = []
        for key in (
            "archive_month_link_count",
            "archive_month_links",
            "count",
            "fetched_page_urls",
            "items",
            "source_url",
            "stop_reason",
        ):
            payload = _fixture_payload()
            del payload[key]
            payloads.append(payload)

        for key in ("published_at", "source_categories", "title", "url"):
            payload = _fixture_payload()
            del payload["items"][0][key]
            payloads.append(payload)

        for index, payload in enumerate(payloads):
            with (
                self.subTest(index=index),
                self.assertRaisesRegex(
                    ValueError,
                    "スナップショットの必須キーが不足しています。",
                ),
            ):
                self._load_payload(payload)

    def test_invalid_value_types_are_rejected(self) -> None:
        """トップレベルとitemの値を暗黙変換せず拒否すること"""

        replacements = (
            (("count",), True),
            (("items",), {}),
            (("source_url",), 1),
            (("archive_month_link_count",), "1"),
            (("archive_month_links",), "archive"),
            (("fetched_page_urls",), [1]),
            (("stop_reason",), 1),
            (("items", 0), "item"),
            (("items", 0, "title"), 1),
            (("items", 0, "published_at"), 20260829),
            (("items", 0, "url"), 1),
            (("items", 0, "source_categories"), "総合政策"),
            (("items", 0, "source_categories"), [1]),
        )

        for path, value in replacements:
            payload = _fixture_payload()
            _replace_nested_value(payload, path, value)
            with (
                self.subTest(path=path),
                self.assertRaisesRegex(
                    ValueError,
                    "スナップショットの値の型が不正です。",
                ),
            ):
                self._load_payload(payload)

    def test_count_mismatches_are_rejected(self) -> None:
        """count、items要素数、期待件数の不一致を拒否すること"""

        count_mismatch = _fixture_payload()
        count_mismatch["count"] = 1
        length_mismatch = _fixture_payload()
        length_mismatch["items"].pop()

        for payload in (count_mismatch, length_mismatch):
            with self.assertRaisesRegex(
                ValueError,
                "スナップショットの件数が期待値と一致しません。",
            ):
                self._load_payload(payload)

    def test_duplicate_normalized_urls_are_rejected(self) -> None:
        """保存DTOで同じ値になる詳細ページURLを拒否すること"""

        payload = _fixture_payload()
        payload["items"][1]["url"] = (
            f" {payload['items'][0]['url']} "
        )

        with self.assertRaisesRegex(
            ValueError,
            "スナップショットの詳細ページURLが重複しています。",
        ):
            self._load_payload(payload)

    def test_invalid_save_dto_is_rejected_without_payload_value(self) -> None:
        """保存DTO不正時に入力本文を例外へ含めないこと"""

        invalid_title = "本文へ出力しない識別文字列"
        payload = _fixture_payload()
        payload["items"][0]["title"] = invalid_title
        payload["items"][0]["url"] = "ftp://example.test/invalid"

        with self.assertRaisesRegex(
            ValueError,
            "報道発表を保存DTOへ変換できません。",
        ) as raised:
            self._load_payload(payload)

        self.assertNotIn(invalid_title, str(raised.exception))
        self.assertNotIn(payload["items"][0]["url"], str(raised.exception))

    def test_sha256_mismatch_is_rejected(self) -> None:
        """入力ファイルのSHA-256不一致を拒否すること"""

        with self.assertRaisesRegex(
            ValueError,
            "スナップショットのSHA-256が期待値と一致しません。",
        ):
            self._load_snapshot(
                _FIXTURE_PATH,
                expected_sha256="0" * 64,
            )

    def test_naive_fetched_at_is_rejected(self) -> None:
        """timezone情報のない取得完了時刻を拒否すること"""

        with self.assertRaisesRegex(
            ValueError,
            "取得完了時刻はtimezone awareである必要があります。",
        ):
            self._load_snapshot(
                _FIXTURE_PATH,
                fetched_at_text="2026-08-29T13:45:27.408274",
            )

    def _load_payload(self, payload: dict[str, object]):
        snapshot_bytes = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode()
        snapshot_path = self._write_bytes("snapshot.json", snapshot_bytes)
        return self._load_snapshot(
            snapshot_path,
            expected_sha256=_sha256(snapshot_bytes),
        )

    def _load_snapshot(
        self,
        snapshot_path: Path,
        *,
        expected_sha256: str = _FIXTURE_SHA256,
        fetched_at_text: str = _FETCHED_AT_TEXT,
    ):
        validation = importlib.import_module(
            "integration_tests.real_snapshot_validation"
        )
        return validation.load_validated_snapshot(
            snapshot_path,
            expected_count=2,
            expected_sha256=expected_sha256,
            fetched_at_text=fetched_at_text,
        )

    def _write_bytes(self, name: str, value: bytes) -> Path:
        snapshot_path = Path(self.temporary_directory.name) / name
        snapshot_path.write_bytes(value)
        return snapshot_path


def _fixture_payload() -> dict[str, object]:
    return deepcopy(json.loads(_FIXTURE_PATH.read_text(encoding="utf-8")))


def _replace_nested_value(
    payload: dict[str, object],
    path: tuple[str | int, ...],
    value: object,
) -> None:
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


if __name__ == "__main__":
    unittest.main()
