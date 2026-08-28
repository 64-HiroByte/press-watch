"""スクレイパーパッケージをCLIとして実行する入口"""

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
from time import monotonic, sleep

from .crawl_state import CrawlState
from .env_press import (
    CHARSET,
    PRESS_INDEX_URL,
    ArchiveMonthLink,
    CrawlStopReason,
    PressRelease,
    REQUEST_INTERVAL_SECONDS,
    _RequestRateLimiter,
    crawl_press_releases,
    fetch_press_page_html,
    parse_archive_month_links,
    parse_press_releases,
)


JSON_OUTPUT_ENCODING = 'utf-8'
OUTPUT_PARENT_NOT_FOUND_REASON = 'output parent directory does not exist'
CREDENTIALS_IN_URL_RE = re.compile(r'(?i)(https?://)[^/@\s]+@')
MAX_DIAGNOSTIC_VALUE_LENGTH = 1000


def main() -> int:
    """報道発表一覧HTMLを取得または読み込み、解析結果をJSONで出力

    Returns:
        正常終了時の終了コード
    """

    parser = argparse.ArgumentParser(
        description='Fetch one Ministry of the Environment press list page.',
    )
    parser.add_argument(
        '--url',
        default=PRESS_INDEX_URL,
        help='HTTP(S) press list page URL to fetch.',
    )
    parser.add_argument(
        '--from-file',
        type=Path,
        help='Parse a saved HTML file instead of fetching.',
    )
    parser.add_argument(
        '--archive-month-limit',
        type=int,
        help='Number of archive month pages to fetch after the index page.',
    )
    parser.add_argument(
        '--all-archive-months',
        action='store_true',
        help='Fetch all archive month pages found on the index page.',
    )
    parser.add_argument(
        '--known-release-urls-file',
        type=Path,
        help='Read known press release URLs from this newline-delimited file.',
    )
    parser.add_argument(
        '--crawl-state-dir',
        type=Path,
        help='Store local archive crawl state in this directory.',
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from an existing crawl state manifest.',
    )
    parser.add_argument(
        '--refetch-invalid-pages',
        action='store_true',
        help='Refetch invalid saved pages during an explicit resume.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Write the same JSON snapshot as stdout to this path.',
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Write progress messages to stderr.',
    )
    parser.add_argument(
        '--no-stdout-json',
        action='store_true',
        help='Do not write the JSON snapshot to stdout.',
    )
    args = parser.parse_args()

    archive_month_limit = args.archive_month_limit
    if archive_month_limit is not None and archive_month_limit < 0:
        parser.error(
            '--archive-month-limit must be greater than or equal to 0.'
        )
    if args.from_file is not None and args.all_archive_months:
        parser.error('--from-file cannot be used with --all-archive-months.')
    has_archive_month_limit = (
        archive_month_limit is not None and archive_month_limit > 0
    )
    if args.from_file is not None and has_archive_month_limit:
        parser.error('--from-file cannot be used with --archive-month-limit.')
    if args.all_archive_months and archive_month_limit is not None:
        parser.error(
            '--archive-month-limit cannot be used with --all-archive-months.'
        )
    if args.known_release_urls_file is not None and not (
        args.all_archive_months or has_archive_month_limit
    ):
        parser.error(
            '--known-release-urls-file requires '
            '--archive-month-limit greater than 0 or --all-archive-months.'
        )
    if args.resume and args.crawl_state_dir is None:
        parser.error('--resume requires --crawl-state-dir.')
    if args.refetch_invalid_pages and not args.resume:
        parser.error('--refetch-invalid-pages requires --resume.')
    if (
        args.crawl_state_dir is not None
        and args.known_release_urls_file is not None
    ):
        parser.error(
            '--known-release-urls-file cannot be used with '
            '--crawl-state-dir.'
        )
    if args.crawl_state_dir is not None and args.from_file is not None:
        parser.error('--from-file cannot be used with --crawl-state-dir.')
    if args.crawl_state_dir is not None and not (
        args.all_archive_months or has_archive_month_limit
    ):
        parser.error(
            '--crawl-state-dir requires --archive-month-limit greater than 0 '
            'or --all-archive-months.'
        )
    if args.no_stdout_json and args.output is None:
        parser.error('--no-stdout-json requires --output.')
    if (
        args.crawl_state_dir is not None
        and args.output is not None
        and _is_path_within(args.output, args.crawl_state_dir)
    ):
        parser.error('--output must be outside --crawl-state-dir.')

    error_target = (
        str(args.from_file) if args.from_file is not None else args.url
    )

    # 成功時だけJSONをstdoutへ出す。途中で失敗した場合は、
    # 途中結果を出さずにstderrと終了コードで失敗を伝える。
    try:
        if args.output is not None:
            error_target = str(args.output)
            _validate_output_path(args.output)
            error_target = (
                str(args.from_file)
                if args.from_file is not None
                else args.url
            )

        archive_month_limit_value = archive_month_limit or 0
        known_release_urls: tuple[str, ...] = ()
        if args.known_release_urls_file is not None:
            error_target = str(args.known_release_urls_file)
            known_release_urls = _read_known_release_urls(
                args.known_release_urls_file,
            )
            error_target = (
                str(args.from_file)
                if args.from_file is not None
                else args.url
            )

        if args.all_archive_months or archive_month_limit_value > 0:
            source_url = args.url

            def progress(message: str) -> None:
                _print_progress(args.verbose, message)

            rate_limiter = _RequestRateLimiter(
                interval_seconds=REQUEST_INTERVAL_SECONDS,
                clock=monotonic,
                sleeper=sleep,
                progress=progress,
            )

            def network_fetcher(url: str) -> str:
                nonlocal error_target

                # 取得に失敗したとき、stderrへそのURLを表示できるようにする。
                error_target = url
                return fetch_press_page_html(
                    url,
                    rate_limiter=rate_limiter,
                )

            crawl_state: CrawlState | None = None
            if args.crawl_state_dir is not None:
                error_target = str(args.crawl_state_dir)
                if args.resume:
                    crawl_state = CrawlState.resume(
                        args.crawl_state_dir,
                        start_url=args.url,
                        archive_month_limit=archive_month_limit_value,
                        all_archive_months=args.all_archive_months,
                        refetch_invalid_pages=args.refetch_invalid_pages,
                    )
                else:
                    crawl_state = CrawlState.create(
                        args.crawl_state_dir,
                        start_url=args.url,
                        archive_month_limit=archive_month_limit_value,
                        all_archive_months=args.all_archive_months,
                    )
                error_target = args.url

            def fetcher(url: str) -> str:
                if crawl_state is None:
                    return network_fetcher(url)
                return crawl_state.load_or_fetch(
                    url,
                    network_fetcher,
                    progress=progress,
                )

            crawl_result = crawl_press_releases(
                start_url=args.url,
                archive_month_limit=archive_month_limit_value,
                all_archive_months=args.all_archive_months,
                fetcher=fetcher,
                known_release_urls=known_release_urls,
                request_interval_seconds=REQUEST_INTERVAL_SECONDS,
                sleeper=sleep,
                progress=progress,
                observer=crawl_state,
            )
            if crawl_state is not None:
                crawl_state.mark_complete(crawl_result.stop_reason)
            releases = crawl_result.releases
            archive_month_links = crawl_result.archive_month_links
            fetched_page_urls = crawl_result.fetched_page_urls
            stop_reason = crawl_result.stop_reason
        elif args.from_file is not None:
            _print_progress(args.verbose, f'reading file: {args.from_file}')
            html = args.from_file.read_text(encoding=CHARSET)
            source_url = str(args.from_file)
            base_url = PRESS_INDEX_URL
            releases = parse_press_releases(html, base_url=base_url)
            archive_month_links = parse_archive_month_links(
                html,
                base_url=base_url,
            )
            fetched_page_urls: list[str] = []
            stop_reason = None
        else:
            def progress(message: str) -> None:
                _print_progress(args.verbose, message)

            rate_limiter = _RequestRateLimiter(
                interval_seconds=REQUEST_INTERVAL_SECONDS,
                clock=monotonic,
                sleeper=sleep,
                progress=progress,
            )
            html = fetch_press_page_html(
                args.url,
                rate_limiter=rate_limiter,
            )
            source_url = args.url
            base_url = args.url
            releases = parse_press_releases(html, base_url=base_url)
            archive_month_links = parse_archive_month_links(
                html,
                base_url=base_url,
            )
            fetched_page_urls = [source_url]
            stop_reason = None

        json_output = _build_snapshot_json(
            source_url=source_url,
            releases=releases,
            archive_month_links=archive_month_links,
            fetched_page_urls=fetched_page_urls,
            stop_reason=stop_reason,
        )

        if args.output is not None:
            error_target = str(args.output)
            args.output.write_text(
                json_output,
                encoding=JSON_OUTPUT_ENCODING,
            )

        if not args.no_stdout_json:
            error_target = 'stdout'
            _write_stdout_json(json_output)
        return 0
    except Exception as exc:
        _print_runtime_error(error_target, exc)
        return 1


def _build_snapshot_json(
    *,
    source_url: str,
    releases: list[PressRelease] | tuple[PressRelease, ...],
    archive_month_links: list[ArchiveMonthLink] | tuple[ArchiveMonthLink, ...],
    fetched_page_urls: list[str] | tuple[str, ...],
    stop_reason: CrawlStopReason | None,
) -> str:
    """CLIが出力するJSONスナップショット文字列を生成

    Args:
        source_url: CLI入力元としてJSONへ記録するURLまたはファイルパス
        releases: JSONのitemsへ変換する報道発表
        archive_month_links: JSONへ含める月別リンク候補
        fetched_page_urls: 報道発表取得対象として解析したページURL
        stop_reason: 月別巡回が正常終了した理由

    Returns:
        stdoutと `--output` に共通で使う改行付きJSON文字列
    """

    items = [
        {
            **asdict(item),
            'published_at': item.published_at.isoformat(),
        }
        for item in releases
    ]
    archive_month_link_items = [
        asdict(item) for item in archive_month_links
    ]

    json_text = json.dumps(
        {
            'source_url': source_url,
            'count': len(releases),
            'archive_month_link_count': len(archive_month_links),
            'archive_month_links': archive_month_link_items,
            'fetched_page_urls': fetched_page_urls,
            'stop_reason': stop_reason,
            'items': items,
        },
        ensure_ascii=False,
        indent=2,
    )
    return f'{json_text}\n'


def _validate_output_path(path: Path) -> None:
    """JSONスナップショット出力先の事前検証

    Args:
        path: `--output` に指定された出力先パス

    Raises:
        FileNotFoundError: 親ディレクトリが存在しない場合
    """

    if not path.parent.exists():
        raise FileNotFoundError(
            f'{OUTPUT_PARENT_NOT_FOUND_REASON}: {path.parent}'
        )


def _is_path_within(path: Path, directory: Path) -> bool:
    """パスが指定ディレクトリ自身または配下を指すか判定

    Args:
        path: 判定するパス
        directory: 基準となるディレクトリ

    Returns:
        同一パスまたは配下ならTrue
    """

    resolved_path = path.resolve(strict=False)
    resolved_directory = directory.resolve(strict=False)
    return (
        resolved_path == resolved_directory
        or resolved_directory in resolved_path.parents
    )


def _read_known_release_urls(path: Path) -> tuple[str, ...]:
    """既知URLファイルから報道発表詳細ページURLを読み込む

    Args:
        path: 改行区切りの既知URLファイル

    Returns:
        空行を除外した既知URLのタプル
    """

    return tuple(
        line
        for raw_line in path.read_text(
            encoding=JSON_OUTPUT_ENCODING,
        ).splitlines()
        if (line := raw_line.strip())
    )


def _print_progress(enabled: bool, message: str) -> None:
    """CLIの進捗メッセージをstderrへ出力

    Args:
        enabled: 進捗を出力するかどうか
        message: stderrへ出す進捗メッセージ
    """

    if enabled:
        print(_one_line(message), file=sys.stderr, flush=True)


def _write_stdout_json(json_text: str) -> None:
    """JSONスナップショットをstdoutへ書き出してflush

    Args:
        json_text: stdoutへ出す改行付きJSON文字列
    """

    try:
        sys.stdout.write(json_text)
        sys.stdout.flush()
    except BrokenPipeError:
        _redirect_stdout_after_broken_pipe(sys.stdout)
        raise


def _redirect_stdout_after_broken_pipe(output: object) -> None:
    """Python終了時のstdout再flushを破棄先へ切り替え

    Args:
        output: JSON出力でBrokenPipeErrorが発生した出力先
    """

    if output is not sys.stdout:
        return

    try:
        stdout_fd = output.fileno()
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(devnull_fd, stdout_fd)
        finally:
            os.close(devnull_fd)
    except (AttributeError, OSError, TypeError, ValueError):
        # 元の出力エラーを優先し、破棄先への切り替え失敗で置き換えない。
        return


def _print_runtime_error(target: str, exc: Exception) -> None:
    """実行時エラーをCLI向けの簡潔な形式でstderrへ出力"""

    # 例外メッセージに改行が含まれても、stderrでは1行で読める形にする。
    reason = _one_line(str(exc)) or 'no detail'
    print(
        (
            'error: '
            f'target={_one_line(target)} '
            f'exception={type(exc).__name__} '
            f'reason={reason}'
        ),
        file=sys.stderr,
    )


def _one_line(value: str) -> str:
    """CLIエラーへ埋め込む文字列を1行へ正規化

    Args:
        value: エラーへ埋め込む文字列

    Returns:
        連続空白を1つにまとめた1行文字列
    """

    redacted_value = CREDENTIALS_IN_URL_RE.sub(
        r'\1[redacted]@',
        value,
    )
    one_line_value = ' '.join(redacted_value.split())
    one_line_value = ''.join(
        character if character.isprintable() else repr(character)[1:-1]
        for character in one_line_value
    )
    if len(one_line_value) > MAX_DIAGNOSTIC_VALUE_LENGTH:
        return (
            f'{one_line_value[:MAX_DIAGNOSTIC_VALUE_LENGTH - 3]}...'
        )
    return one_line_value


if __name__ == '__main__':
    raise SystemExit(main())
