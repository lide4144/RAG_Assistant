from __future__ import annotations

import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None


class FileLockTimeoutError(TimeoutError):
    pass


@contextmanager
def atomic_text_writer(target: str | Path, *, encoding: str = "utf-8") -> Iterator[TextIO]:
    output = Path(target)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=str(output.parent))
    tmp_path = Path(tmp_name)
    stream = os.fdopen(fd, "w", encoding=encoding)
    try:
        yield stream
        stream.flush()
        os.fsync(stream.fileno())
        stream.close()
        tmp_path.replace(output)
    except Exception:
        try:
            stream.close()
        finally:
            if tmp_path.exists():
                tmp_path.unlink()
        raise


@contextmanager
def file_lock(lock_path: str | Path, *, timeout_sec: float = 10.0, poll_interval_sec: float = 0.1) -> Iterator[None]:
    lock_file = Path(lock_path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o644)
    start = time.monotonic()
    acquired = False
    try:
        if fcntl is None:  # pragma: no cover
            acquired = True
        else:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except BlockingIOError:
                    if time.monotonic() - start >= timeout_sec:
                        raise FileLockTimeoutError(f"lock timeout for {lock_file}")
                    time.sleep(poll_interval_sec)
        yield
    finally:
        if fcntl is not None and acquired:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
        os.close(fd)
