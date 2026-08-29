"""File store abstraction.

Uploaded CSVs live on disk (or, later, in object storage) and only their *key*
is written to the database.  Callers never build a path themselves, so pointing
``FileStore`` at S3 is a one-class change with no ripples.

Path handling is deliberately paranoid: the caller-supplied filename is reduced
to a safe stem and the resolved path is asserted to sit inside the root, so a
crafted ``../../`` name cannot escape the upload directory.
"""

from __future__ import annotations

import re
import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from app.core.errors import ErrorCode, IngestionError, NotFoundError

_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_stem(filename: str) -> str:
    stem = _SAFE_RE.sub("_", Path(filename).name).strip("._")
    return (stem or "upload")[:120]


class FileStore(ABC):
    @abstractmethod
    def save(self, fileobj: BinaryIO, filename: str, *, prefix: str = "") -> tuple[str, int]:
        """Persist a stream.  Returns ``(storage_key, bytes_written)``."""

    @abstractmethod
    def path_for(self, key: str) -> Path:
        """Local path for reading.  Object stores would download to a temp file."""

    @abstractmethod
    def delete(self, key: str) -> None: ...


class LocalFileStore(FileStore):
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        if not candidate.is_relative_to(self.root):
            raise IngestionError(
                "Invalid storage key.",
                code=ErrorCode.UNREADABLE_FILE,
                context={"key": key},
            )
        return candidate

    def save(self, fileobj: BinaryIO, filename: str, *, prefix: str = "") -> tuple[str, int]:
        key = f"{prefix}{uuid.uuid4().hex[:12]}__{safe_stem(filename)}"
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        # copyfileobj streams in fixed-size blocks -- a 2 GB upload never
        # becomes a 2 GB bytes object.
        with target.open("wb") as out:
            shutil.copyfileobj(fileobj, out, length=1 << 20)
        return key, target.stat().st_size

    def path_for(self, key: str) -> Path:
        path = self._resolve(key)
        if not path.exists():
            raise NotFoundError(
                f"Stored file '{key}' is missing.",
                code=ErrorCode.DATASET_NOT_FOUND,
            )
        return path

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        path.unlink(missing_ok=True)


_store: FileStore | None = None


def get_file_store() -> FileStore:
    global _store
    if _store is None:
        from app.core.config import get_settings

        settings = get_settings()
        if settings.storage_backend == "local":
            _store = LocalFileStore(settings.upload_storage_path)
        else:  # pragma: no cover - only one backend implemented today
            raise IngestionError(f"Unknown storage backend: {settings.storage_backend}")
    return _store


def set_file_store(store: FileStore) -> None:
    """Test hook."""
    global _store
    _store = store
