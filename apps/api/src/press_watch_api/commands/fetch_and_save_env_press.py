"""環境省報道発表を手動で取得しDBへ保存するCLI入口"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Protocol

from sqlalchemy.orm import Session

from press_watch_api.services.press_release_save import (
    list_known_release_urls_for_crawl,
    save_press_releases,
)


SCRAPER_COMMAND_FAILED_REASON = "scraper command failed"
POST_COMMIT_OUTPUT_FAILED_REASON = (
    "database commit succeeded but result output failed"
)
DEFAULT_KNOWN_RELEASE_MONTHS = 3
CREDENTIALS_IN_URL_RE = re.compile(r"(?i)(https?://)[^/@\s]+@")
MAX_DIAGNOSTIC_VALUE_LENGTH = 1000
SCRAPER_ENV_KEYS = (
    "HOME",
    "PATH",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "XDG_CACHE_HOME",
    "UV_CACHE_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


class SessionFactory(Protocol):
    """DBセッションを生成する関数

    テストではMockセッションを返す関数に差し替え、通常実行では
    `press_watch_api.db.SessionLocal` を使う。
    """

    def __call__(self) -> Session:
        """SQLAlchemyセッションを生成

        Returns:
            取得・保存処理で使うDBセッション
        """


class ParsedArgs(Protocol):
    """手動取得・保存コマンドで使う引数

    Attributes:
        url: scraper CLIへ渡す報道発表一覧ページURL
        from_file: scraper CLIへ渡す保存済みHTMLのパス
        archive_month_limit: scraper CLIへ渡す月別ページ取得上限
        all_archive_months: scraper CLIへすべての月別ページ取得を指定するか
        known_release_months: 既知URLとしてDBから取得する直近月数
        verbose: scraper CLIの進捗stderrを表示するかどうか
    """

    url: str
    from_file: Path | None
    archive_month_limit: int | None
    all_archive_months: bool
    known_release_months: int
    verbose: bool


@dataclass(frozen=True)
class ScraperCliRelease:
    """scraper CLI のJSONから復元した報道発表

    Attributes:
        title: 報道発表のタイトル
        published_at: 報道発表日
        url: 報道発表詳細ページのURL
        source_categories: 取得元ページに表示されたカテゴリ
    """

    title: str
    published_at: date
    url: str
    source_categories: tuple[str, ...]


@dataclass(frozen=True)
class CollectedPressReleases:
    """手動取得・保存でDBへ渡す取得結果

    Attributes:
        source_url: scraper CLIで指定された取得元URLまたはファイルパス
        releases: DB保存serviceへ渡す報道発表
        fetched_page_urls: scraper CLIが取得対象として解析したページURL
        stop_reason: 月別巡回が正常終了した理由
    """

    source_url: str
    releases: tuple[ScraperCliRelease, ...]
    fetched_page_urls: tuple[str, ...]
    stop_reason: str | None

    @property
    def fetched_count(self) -> int:
        """取得件数

        Returns:
            scraper CLIから受け取った報道発表の件数
        """

        return len(self.releases)


@dataclass(frozen=True)
class FetchAndSaveResult:
    """手動取得・保存コマンドの実行結果

    Attributes:
        source_url: 取得対象のURLまたはファイルパス
        fetched_count: scraper CLIから受け取った件数
        saved_count: DBへ新規保存した件数
        skipped_count: 既存source_urlと重複して保存しなかった件数
        fetched_page_urls: scraper CLIが取得対象として解析したページURL
        stop_reason: 月別巡回が正常終了した理由
    """

    source_url: str
    fetched_count: int
    saved_count: int
    skipped_count: int
    fetched_page_urls: tuple[str, ...]
    stop_reason: str | None

    def to_json_dict(self) -> dict[str, object]:
        """stdoutへ出すJSON用の辞書へ変換

        Returns:
            手動取得・保存コマンドの結果として出力するJSON互換の辞書
        """

        return {
            "source_url": self.source_url,
            "fetched_count": self.fetched_count,
            "saved_count": self.saved_count,
            "skipped_count": self.skipped_count,
            "fetched_page_urls": list(self.fetched_page_urls),
            "stop_reason": self.stop_reason,
        }


CollectReleases = Callable[
    [ParsedArgs, object, Collection[str]],
    CollectedPressReleases,
]


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: SessionFactory | None = None,
    collect_releases: CollectReleases | None = None,
    stdout: object | None = None,
    stderr: object | None = None,
) -> int:
    """手動取得・保存コマンドを実行

    Args:
        argv: プログラム名を除くCLI引数
        session_factory: DBセッションを生成する関数
        collect_releases: scraper 取得結果を返す関数
        stdout: 実行結果JSONの出力先
        stderr: エラーの出力先

    Returns:
        正常終了時は0、実行時失敗時は1
    """

    output = stdout or sys.stdout
    error_output = stderr or sys.stderr
    parser = _build_parser()
    args = parser.parse_args(argv)
    _validate_args(parser, args)
    session_factory = session_factory or _load_session_factory()
    collect_releases = collect_releases or _collect_releases_from_scraper_cli
    error_target = _error_target(args)

    session: Session | None = None
    committed = False
    try:
        known_release_urls = _load_known_release_urls(
            session_factory,
            args,
        )
        collected = collect_releases(
            args,
            error_output,
            known_release_urls,
        )
        session = session_factory()
        save_result = save_press_releases(
            session,
            collected.releases,
        )
        result = FetchAndSaveResult(
            source_url=collected.source_url,
            fetched_count=collected.fetched_count,
            saved_count=save_result.saved_count,
            skipped_count=save_result.skipped_count,
            fetched_page_urls=collected.fetched_page_urls,
            stop_reason=collected.stop_reason,
        )
        session.commit()
        committed = True
        _write_json(output, result.to_json_dict())
        return 0
    except Exception as exc:
        if session is not None and not committed:
            session.rollback()
        if committed:
            _print_post_commit_output_error(
                error_output,
                error_target,
                exc,
            )
        else:
            _print_runtime_error(error_output, error_target, exc)
        return 1
    finally:
        if session is not None:
            session.close()


def _build_parser() -> argparse.ArgumentParser:
    """手動取得・保存コマンドの引数定義を生成

    Returns:
        `fetch_and_save_env_press` のCLI引数を解釈するparser
    """

    parser = argparse.ArgumentParser(
        description=(
            "Fetch Ministry of the Environment press releases "
            "and save them to the database."
        ),
    )
    parser.add_argument(
        "--url",
        default="https://www.env.go.jp/press/index.html",
        help="HTTP(S) press list page URL to fetch.",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Parse a saved HTML file through the scraper CLI.",
    )
    parser.add_argument(
        "--archive-month-limit",
        type=int,
        help="Number of archive month pages to fetch.",
    )
    parser.add_argument(
        "--all-archive-months",
        action="store_true",
        help="Fetch all archive month pages found on the index page.",
    )
    parser.add_argument(
        "--known-release-months",
        type=int,
        default=DEFAULT_KNOWN_RELEASE_MONTHS,
        help=(
            "Number of recent published months whose saved URLs are treated "
            "as known during archive crawling. Defaults to 3."
        ),
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Write scraper progress messages to stderr.",
    )
    return parser


def _load_session_factory() -> SessionFactory:
    """DB設定を読み込み、コマンド実行用のセッション生成関数を返す

    Returns:
        DB接続設定を反映したSQLAlchemyセッション生成関数
    """

    from press_watch_api.db import SessionLocal

    return SessionLocal


def _load_known_release_urls(
    session_factory: SessionFactory,
    args: ParsedArgs,
) -> tuple[str, ...]:
    """月別巡回の既知URLを短時間のDB Sessionで取得

    Args:
        session_factory: DBセッションを生成する関数
        args: 手動取得・保存コマンドで受け取ったCLI引数

    Returns:
        scraper 側へ取得済みとして渡す報道発表URL
    """

    if not _uses_archive_crawl(args):
        return ()

    session = session_factory()
    try:
        return list_known_release_urls_for_crawl(
            session,
            month_count=args.known_release_months,
        )
    finally:
        # scraper のHTTP巡回中にDBトランザクションを保持しない。
        session.close()


def _collect_releases_from_scraper_cli(
    args: ParsedArgs,
    stderr: object,
    known_release_urls: Collection[str],
) -> CollectedPressReleases:
    """既存scraper CLIを実行してJSONスナップショットを取得

    Args:
        args: 手動取得・保存コマンドで受け取ったCLI引数
        stderr: verbose時にscraper CLIの進捗を転送する出力先
        known_release_urls: scraper 側で取得済みとして扱う報道発表URL

    Returns:
        scraper CLIのstdout JSONから復元した取得結果

    Raises:
        RuntimeError: scraper CLIが正常終了しなかった場合
        json.JSONDecodeError: scraper CLIのstdoutがJSONとして読めない場合
        KeyError: scraper CLIのJSONに必要なキーがない場合
    """

    scraper_dir = _scraper_package_dir()
    env = _scraper_env(scraper_dir)
    known_release_urls_file: Path | None = None
    try:
        if known_release_urls and _uses_archive_crawl(args):
            known_release_urls_file = _write_known_release_urls_file(
                known_release_urls,
            )
        command = _scraper_command(
            args,
            known_release_urls_file=known_release_urls_file,
        )
        completed = subprocess.run(
            command,
            cwd=scraper_dir,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
    finally:
        if known_release_urls_file is not None:
            known_release_urls_file.unlink(missing_ok=True)

    if completed.returncode != 0:
        reason = _one_line(completed.stderr) or (
            f"exit code {completed.returncode}"
        )
        raise RuntimeError(
            f"{SCRAPER_COMMAND_FAILED_REASON}: "
            f"exit_code={completed.returncode} stderr={reason}"
        )

    if args.verbose and completed.stderr:
        stderr.write(completed.stderr)

    return _parse_scraper_snapshot(completed.stdout)


def _scraper_command(
    args: ParsedArgs,
    *,
    known_release_urls_file: Path | None = None,
) -> list[str]:
    """scraper CLIを呼び出すコマンド列を組み立てる

    Args:
        args: scraper CLIへ渡す取得条件
        known_release_urls_file: scraper CLIへ渡す既知URLファイル

    Returns:
        `subprocess.run()` に渡すコマンド引数列
    """

    command = [
        "uv",
        "run",
        "--locked",
        "python",
        "-m",
        "press_watch_scraper",
        "--url",
        args.url,
    ]
    if args.from_file is not None:
        command.extend(["--from-file", str(args.from_file.resolve())])
    if args.archive_month_limit is not None:
        command.extend(
            ["--archive-month-limit", str(args.archive_month_limit)]
        )
    if args.all_archive_months:
        command.append("--all-archive-months")
    if known_release_urls_file is not None:
        command.extend(
            ["--known-release-urls-file", str(known_release_urls_file)]
        )
    if args.verbose:
        command.append("--verbose")
    return command


def _write_known_release_urls_file(
    known_release_urls: Collection[str],
) -> Path:
    """scraper CLIへ渡す既知URLファイルを作成

    Args:
        known_release_urls: DB保存済みとして扱う報道発表詳細ページURL

    Returns:
        改行区切りで既知URLを書き出した一時ファイルのパス
    """

    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
        ) as file:
            path = Path(file.name)
            for source_url in sorted(set(known_release_urls)):
                file.write(f"{source_url}\n")
    except Exception:
        if path is not None:
            path.unlink(missing_ok=True)
        raise

    if path is None:
        raise RuntimeError("known release URL temporary file was not created")
    return path


def _validate_args(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    """手動取得・保存コマンドの引数組み合わせを検証

    Args:
        parser: エラー表示に使うCLI parser
        args: argparseで解釈済みのCLI引数

    Raises:
        SystemExit: argparseのエラーとして不正な組み合わせを拒否する場合
    """

    if args.from_file is not None and args.all_archive_months:
        parser.error(
            "--from-file cannot be used with --all-archive-months."
        )
    if args.all_archive_months and args.archive_month_limit is not None:
        parser.error(
            "--archive-month-limit cannot be used with --all-archive-months."
        )
    if args.known_release_months <= 0:
        parser.error("--known-release-months must be greater than 0.")


def _uses_archive_crawl(args: ParsedArgs) -> bool:
    """月別アーカイブ巡回を行う引数か判定

    Args:
        args: 手動取得・保存コマンドで受け取ったCLI引数

    Returns:
        scraper CLIで月別アーカイブへ進む場合はTrue
    """

    return args.all_archive_months or (
        args.archive_month_limit is not None
        and args.archive_month_limit > 0
    )


def _scraper_env(scraper_dir: Path) -> dict[str, str]:
    """scraper CLIに必要な環境変数を作成

    Args:
        scraper_dir: scraperパッケージのディレクトリ

    Returns:
        実行環境とHTTP取得に必要な値へ限定した環境変数
    """

    env = {
        key: value
        for key in SCRAPER_ENV_KEYS
        if (value := os.environ.get(key)) is not None
    }
    scraper_src = str(scraper_dir / "src")
    env["PYTHONPATH"] = scraper_src
    env["PYTHONUTF8"] = "1"
    return env


def _scraper_package_dir() -> Path:
    """リポジトリ内のscraperパッケージディレクトリを返す

    Returns:
        `packages/scraper` の絶対パス
    """

    repo_root = Path(__file__).resolve().parents[5]
    return repo_root / "packages" / "scraper"


def _parse_scraper_snapshot(json_text: str) -> CollectedPressReleases:
    """scraper CLIのJSONを手動取得・保存用データへ変換

    Args:
        json_text: scraper CLIがstdoutへ出したJSONスナップショット

    Returns:
        DB保存serviceへ渡せる形に復元した取得結果

    Raises:
        json.JSONDecodeError: JSONとして読めない場合
        KeyError: 必要なキーがJSONに存在しない場合
        ValueError: `published_at` が日付文字列として読めない場合
    """

    payload = json.loads(json_text)
    releases = tuple(
        ScraperCliRelease(
            title=str(item["title"]),
            published_at=date.fromisoformat(str(item["published_at"])),
            url=str(item["url"]),
            source_categories=tuple(item.get("source_categories") or ()),
        )
        for item in payload["items"]
    )

    return CollectedPressReleases(
        source_url=str(payload["source_url"]),
        releases=releases,
        fetched_page_urls=tuple(payload.get("fetched_page_urls") or ()),
        stop_reason=payload.get("stop_reason"),
    )


def _write_json(output: object, payload: dict[str, object]) -> None:
    """実行結果JSONをstdoutへ書き出す

    Args:
        output: JSON文字列を書き込む出力先
        payload: JSONとして出力する実行結果
    """

    json_text = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
    )
    output.write(f"{json_text}\n")


def _error_target(args: ParsedArgs) -> str:
    """失敗時stderrに表示する対象を決める

    Args:
        args: 手動取得・保存コマンドで受け取ったCLI引数

    Returns:
        保存済みHTMLパスまたは取得対象URL
    """

    if args.from_file is not None:
        return str(args.from_file)
    return args.url


def _print_runtime_error(
    output: object,
    target: str,
    exc: Exception,
) -> None:
    """実行時エラーをCLI向けの簡潔な形式でstderrへ出力

    Args:
        output: エラー文字列を書き込む出力先
        target: エラー対象として表示するURLまたはファイルパス
        exc: stderrへ種類と理由を出す例外
    """

    print(
        (
            "error: "
            f"target={_one_line(target)} "
            f"exception={type(exc).__name__} "
            f"reason={_one_line(str(exc)) or 'no detail'}"
        ),
        file=output,
    )


def _print_post_commit_output_error(
    output: object,
    target: str,
    exc: Exception,
) -> None:
    """DB確定後の実行結果出力失敗をstderrへ出力

    Args:
        output: エラー文字列を書き込む出力先
        target: エラー対象として表示するURLまたはファイルパス
        exc: stdoutへの出力で発生した例外
    """

    reason = _one_line(str(exc)) or "no detail"
    print(
        (
            "error: "
            f"target={_one_line(target)} "
            f"exception={type(exc).__name__} "
            f"reason={POST_COMMIT_OUTPUT_FAILED_REASON}: {reason}"
        ),
        file=output,
    )


def _one_line(value: str) -> str:
    """stderr向けに改行を含む文字列を1行へ正規化

    Args:
        value: stderrへ埋め込む文字列

    Returns:
        連続空白を1つにまとめた1行文字列
    """

    redacted_value = CREDENTIALS_IN_URL_RE.sub(
        r"\1[redacted]@",
        value,
    )
    one_line_value = " ".join(redacted_value.split())
    one_line_value = "".join(
        character if character.isprintable() else repr(character)[1:-1]
        for character in one_line_value
    )
    if len(one_line_value) > MAX_DIAGNOSTIC_VALUE_LENGTH:
        return (
            f"{one_line_value[:MAX_DIAGNOSTIC_VALUE_LENGTH - 3]}..."
        )
    return one_line_value


if __name__ == "__main__":
    raise SystemExit(main())
