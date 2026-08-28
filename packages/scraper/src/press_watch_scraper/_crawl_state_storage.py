"""ローカル巡回stateのファイル保存と安全性検証"""

import json
import os
from pathlib import Path
import tempfile
from typing import Any

from ._crawl_state_manifest import (
    CrawlStateError,
    JSON_ENCODING,
    MANIFEST_FILENAME,
    PAGES_DIRECTORY_NAME,
)


STATE_DIRECTORY_MODE = 0o700
STATE_FILE_MODE = 0o600


def prepare_new_state_directory(root: Path) -> None:
    """新規state用の空ディレクトリ構成を安全な権限で準備

    Args:
        root: 準備するstateディレクトリ

    Raises:
        CrawlStateError: パスがsymlink、ディレクトリ以外、または空でない場合
    """

    if root.is_symlink():
        raise CrawlStateError('crawl state directory must not be a symlink')
    if root.exists():
        if not root.is_dir():
            raise CrawlStateError('crawl state path must be a directory')
        if any(root.iterdir()):
            raise CrawlStateError('new crawl state directory must be empty')
        os.chmod(root, STATE_DIRECTORY_MODE)
    else:
        if not root.parent.is_dir():
            raise CrawlStateError(
                'crawl state parent directory does not exist'
            )
        root.mkdir(mode=STATE_DIRECTORY_MODE)
        os.chmod(root, STATE_DIRECTORY_MODE)
    pages_directory = root / PAGES_DIRECTORY_NAME
    pages_directory.mkdir(mode=STATE_DIRECTORY_MODE)
    os.chmod(pages_directory, STATE_DIRECTORY_MODE)


def validate_existing_state_directory(root: Path) -> None:
    """既存stateとpagesディレクトリの所有者・権限を検証

    Args:
        root: 検証するstateディレクトリ

    Raises:
        CrawlStateError: ディレクトリ構成、所有者、権限が不正な場合
    """

    if root.is_symlink():
        raise CrawlStateError('crawl state directory must not be a symlink')
    if not root.is_dir():
        raise CrawlStateError('crawl state directory does not exist')
    root_stat = root.stat()
    if hasattr(os, 'geteuid') and root_stat.st_uid != os.geteuid():
        raise CrawlStateError('crawl state directory must be owned by the user')
    if (root_stat.st_mode & 0o777) != STATE_DIRECTORY_MODE:
        raise CrawlStateError(
            'crawl state directory permissions must be 0700'
        )
    pages_directory = root / PAGES_DIRECTORY_NAME
    if pages_directory.is_symlink() or not pages_directory.is_dir():
        raise CrawlStateError('crawl state pages directory is invalid')
    pages_stat = pages_directory.stat()
    if hasattr(os, 'geteuid') and pages_stat.st_uid != os.geteuid():
        raise CrawlStateError(
            'crawl state pages directory must be owned by the user'
        )
    if (pages_stat.st_mode & 0o777) != STATE_DIRECTORY_MODE:
        raise CrawlStateError(
            'crawl state pages directory permissions must be 0700'
        )


def validate_state_file(path: Path, label: str) -> None:
    """state内ファイルの種別・所有者・権限を検証

    Args:
        path: 検証するファイルパス
        label: エラーメッセージに使用する対象名

    Raises:
        CrawlStateError: 通常ファイルでないか所有者・権限が不正な場合
    """

    if path.is_symlink() or not path.is_file():
        raise CrawlStateError(f'{label} is missing or invalid')
    path_stat = path.stat()
    if hasattr(os, 'geteuid') and path_stat.st_uid != os.geteuid():
        raise CrawlStateError(f'{label} must be owned by the user')
    if (path_stat.st_mode & 0o777) != STATE_FILE_MODE:
        raise CrawlStateError(f'{label} permissions must be 0600')


def read_manifest(path: Path) -> dict[str, Any]:
    """stateのmanifestをJSONオブジェクトとして読み込み

    Args:
        path: manifestのファイルパス

    Returns:
        JSONから復元したmanifest

    Raises:
        CrawlStateError: ファイルまたはJSONオブジェクトが不正な場合
    """

    validate_state_file(path, 'crawl state manifest')
    try:
        manifest_value = json.loads(path.read_text(encoding=JSON_ENCODING))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CrawlStateError('crawl state manifest is invalid') from exc
    if not isinstance(manifest_value, dict):
        raise CrawlStateError('crawl state manifest must be an object')
    return manifest_value


def validated_cleanup_entries(
    root: Path,
    manifest: dict[str, Any],
) -> tuple[list[Path], list[Path]]:
    """cleanup対象だけでstateが構成されていることを事前検証

    この関数では削除せず、ディレクトリ内の項目をmanifest管理下の
    HTMLと内部一時ファイルへ分類し、管理外項目がないことを確認する。

    Args:
        root: cleanup対象のstateディレクトリ
        manifest: 検証済みの完了manifest

    Returns:
        manifest管理下のHTMLパスと内部一時ファイルパス

    Raises:
        CrawlStateError: symlink、管理外項目、権限不正を検出した場合
    """

    pages_directory = root / PAGES_DIRECTORY_NAME
    expected_page_paths = {
        root / page['file'] for page in manifest['pages']
    }
    temporary_paths: list[Path] = []

    for entry in root.iterdir():
        if entry in {root / MANIFEST_FILENAME, pages_directory}:
            continue
        if _is_internal_temporary_file(entry, {MANIFEST_FILENAME}):
            temporary_paths.append(entry)
            continue
        raise CrawlStateError(
            f'unmanaged crawl state entry: {entry.name}'
        )

    expected_page_names = {path.name for path in expected_page_paths}
    for entry in pages_directory.iterdir():
        if entry in expected_page_paths:
            continue
        if _is_internal_temporary_file(entry, expected_page_names):
            temporary_paths.append(entry)
            continue
        raise CrawlStateError(
            f'unmanaged crawl state entry: {entry.name}'
        )

    for temporary_path in temporary_paths:
        validate_state_file(temporary_path, 'crawl state temporary file')
    return sorted(expected_page_paths), temporary_paths


def _is_internal_temporary_file(
    path: Path,
    target_names: set[str],
) -> bool:
    """原子的保存で生成される内部一時ファイルか判定

    Args:
        path: 判定するファイルパス
        target_names: 一時ファイルの置換先として許可するファイル名

    Returns:
        許可した置換先の内部一時ファイルならTrue
    """

    if path.is_symlink() or not path.is_file():
        return False
    return any(
        path.name.startswith(f'.{target_name}.')
        and path.name.endswith('.tmp')
        and len(path.name) > len(target_name) + len('...tmp')
        for target_name in target_names
    )


def atomic_write(path: Path, payload: bytes) -> None:
    """一時ファイルを経由してstateファイルを原子的に置換

    一時ファイルと置換後のファイルを`0600`にし、置換前に内容を
    `fsync()`する。失敗時は作成した一時ファイルを削除する。

    Args:
        path: 最終的な保存先パス
        payload: 保存するバイト列
    """

    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f'.{path.name}.',
        suffix='.tmp',
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, STATE_FILE_MODE)
        with os.fdopen(file_descriptor, 'wb') as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, STATE_FILE_MODE)
    except BaseException:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise
