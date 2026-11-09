"""APIと取得ジョブで使うCAの一時配置"""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from tempfile import NamedTemporaryFile


@contextmanager
def certificate_environment() -> Iterator[None]:
    """環境変数のCAを所有者専用ファイルへ展開し、終了時に元の設定へ復元

    Yields:
        CA設定済みの実行区間、CA未指定時は環境を変更しない区間

    Raises:
        RuntimeError: CAが設定済みで空の場合
    """
    certificate = os.getenv("PRESSWATCH_DB_CA_CERT")
    if certificate is None:
        yield
        return
    if not certificate.strip():
        raise RuntimeError("PRESSWATCH_DB_CA_CERT is empty.")

    previous = os.environ.get("PGSSLROOTCERT")
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="presswatch-ca-",
    ) as ca_file:
        ca_file.write(certificate)
        ca_file.flush()
        os.environ["PGSSLROOTCERT"] = ca_file.name
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("PGSSLROOTCERT", None)
            else:
                os.environ["PGSSLROOTCERT"] = previous
