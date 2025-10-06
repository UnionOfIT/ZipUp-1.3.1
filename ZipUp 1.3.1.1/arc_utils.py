import os
import io
import zipfile
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

ARC_KEY = 0x5A

try:
    ZIP_ZSTD = zipfile.ZIP_ZSTD  # type: ignore[attr-defined]
except AttributeError:
    ZIP_ZSTD = None


class XORFile(io.RawIOBase):
    def __init__(self, base: io.BufferedRandom, key: int = ARC_KEY):
        self._base = base
        self._key = key

    def read(self, n: int = -1) -> bytes:  # noqa: D401
        data = self._base.read(n)
        return bytes(b ^ self._key for b in data) if data else data

    def write(self, data: bytes) -> int:  # noqa: D401
        return self._base.write(bytes(b ^ self._key for b in data))

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:  # noqa: D401
        return self._base.seek(offset, whence)

    def tell(self) -> int:  # noqa: D401
        return self._base.tell()

    def flush(self) -> None:  # noqa: D401
        self._base.flush()

    def close(self) -> None:  # noqa: D401
        self._base.close()

    def readable(self) -> bool:  # noqa: D401
        return True

    def writable(self) -> bool:  # noqa: D401
        return True

    def seekable(self) -> bool:  # noqa: D401
        return True

    def truncate(self, size: Optional[int] = None):  # type: ignore[override]
        return self._base.truncate(size)


def compression_for(path: str) -> int:
    if path.lower().endswith('.arc') and ZIP_ZSTD is not None:
        return ZIP_ZSTD
    return zipfile.ZIP_DEFLATED


@contextmanager

def open_zip(path: str, mode: str = 'r') -> Iterator[Tuple[zipfile.ZipFile, Optional[None]]]:
    is_arc = path.lower().endswith('.arc')

    def _open_base(file_mode: str):
        return open(path, file_mode)

    if is_arc:
        if mode == 'r':
            base = _open_base('rb')
        elif mode == 'w':
            base = _open_base('w+b')
        elif mode == 'a':
            base = _open_base('r+b' if os.path.exists(path) else 'w+b')
        else:
            base = _open_base('r+b')
        fileobj: io.RawIOBase = XORFile(base)
    else:
        if mode == 'r':
            base = _open_base('rb')
        elif mode == 'w':
            base = _open_base('w+b')
        elif mode == 'a':
            base = _open_base('r+b' if os.path.exists(path) else 'w+b')
        else:
            base = _open_base('r+b')
        fileobj = base

    kwargs = {}
    comp = compression_for(path)
    if comp == ZIP_ZSTD:
        kwargs["compresslevel"] = 1

    zf = zipfile.ZipFile(fileobj, mode, compression=comp, **kwargs)
    try:
        yield zf, None
    finally:
        zf.close()
        base.close() 