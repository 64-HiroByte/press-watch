"""保存済み報道発表の固定カテゴリを再分類するCLI"""

import argparse
from collections.abc import Callable, Sequence
import json
import os
import sys
from typing import TextIO

from sqlalchemy.orm import Session

from press_watch_api.db import get_session_factory
from press_watch_api.services.fixed_category_classification import FixedCategoryClassificationError
from press_watch_api.services.fixed_category_reclassification import reclassify_press_releases


def main(
    argv: Sequence[str] | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """保存済み全件を再分類し、全体を一括確定

    他の書込み処理を停止してから実行する。
    commit後の出力・close失敗でも終了コードは1になるが、変更は確定済み。

    Args:
        argv: プログラム名を除くCLI引数。省略時はプロセスの引数を使用
        session_factory: 専用Sessionを生成する関数。省略時は既存のDB設定を使用
        stdout: 件数JSONまたはヘルプの出力先
        stderr: 値や例外詳細を含まない診断の出力先

    Returns:
        成功・ヘルプは0、実行失敗・中断は1、引数不正は2
    """

    output = stdout if stdout is not None else sys.stdout
    error_output = stderr if stderr is not None else sys.stderr
    parser = argparse.ArgumentParser(
        description="Reclassify all stored press releases using bundled fixed category rules.",
        add_help=False, exit_on_error=False, allow_abbrev=False,
    )
    parser.add_argument("-h", "--help", action="store_true", help="show this help message and exit")
    try:
        args = parser.parse_args(argv)
    except argparse.ArgumentError as error:
        return 2 if _print_error(error_output, "arguments", False, error) else 1
    except KeyboardInterrupt as error:
        _print_error(error_output, "arguments", False, error)
        return 1
    if args.help:
        try:
            output.write(parser.format_help())
            output.flush()
        except (Exception, KeyboardInterrupt) as error:
            _redirect_stream_after_output_error(output)
            _print_error(error_output, "help", False, error)
            return 1
        return 0

    session: Session | None = None
    commit_succeeded = False
    operation = "configure"
    exit_code = 0
    try:
        factory = session_factory if session_factory is not None else get_session_factory()
        operation = "open_session"
        session = factory()
        operation = "reclassify"
        result = reclassify_press_releases(session)
        operation = "commit"
        session.commit()
        commit_succeeded = True
        operation = "output"
        output.write(json.dumps({
            "processed_count": result.processed_count,
            "matched_count": result.matched_count,
            "classification_count": result.classification_count,
        }) + "\n")
        output.flush()
    except (Exception, KeyboardInterrupt) as error:
        exit_code = 1
        if operation == "output":
            _redirect_stream_after_output_error(output)
        _print_error(error_output, operation, commit_succeeded, error)
        if session is not None and not commit_succeeded:
            try:
                session.rollback()
            except (Exception, KeyboardInterrupt) as cleanup_error:
                _print_error(error_output, "rollback", commit_succeeded, cleanup_error)
    finally:
        if session is not None:
            try:
                session.close()
            except (Exception, KeyboardInterrupt) as cleanup_error:
                exit_code = 1
                _print_error(error_output, "close", commit_succeeded, cleanup_error)
    return exit_code


def _redirect_stream_after_output_error(output: TextIO) -> None:
    """標準ストリームの終了時再flushを破棄先へ切り替え

    Python終了時のflush失敗で終了コードや診断が上書きされることを防ぐ。
    呼出元が渡した独立した出力先は変更しない。
    """

    if output is not sys.stdout and output is not sys.stderr:
        return
    try:
        stream_fd = output.fileno()
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        # 閉じた標準FDを再利用した場合は、破棄先として開いたままにする。
        if devnull_fd != stream_fd:
            try:
                os.dup2(devnull_fd, stream_fd)
            finally:
                os.close(devnull_fd)
    except (AttributeError, OSError, TypeError, ValueError, KeyboardInterrupt):
        return


def _print_error(
    output: TextIO,
    operation: str,
    commit_succeeded: bool,
    error: Exception | KeyboardInterrupt,
) -> bool:
    """例外本文を参照せず、処理段階と固定の理由を出力

    Args:
        output: 診断の出力先
        operation: 失敗した処理段階
        commit_succeeded: commitの正常終了を確認できたか。FalseでもDB未変更とは限らない
        error: 中断・ルール不備の種類の判別にだけ使う例外

    Returns:
        診断の書込みとflushに成功した場合はTrue
    """

    if isinstance(error, KeyboardInterrupt):
        reason = "operation interrupted"
    elif operation == "reclassify" and isinstance(error, FixedCategoryClassificationError):
        reason = "fixed category rules could not be loaded or verified"
    else:
        reason = {
            "arguments": "invalid command arguments",
            "help": "help output failed",
            "configure": "database configuration could not be loaded",
            "reclassify": "reclassification failed",
            "output": "database commit succeeded but result output failed",
        }.get(operation, "database operation failed")
    try:
        print(
            f"error: operation={operation} "
            f"commit_succeeded={str(commit_succeeded).lower()} reason={reason}",
            file=output, flush=True,
        )
    except (Exception, KeyboardInterrupt):
        _redirect_stream_after_output_error(output)
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
