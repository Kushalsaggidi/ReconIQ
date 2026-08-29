"""Chunked tabular readers.

The rest of the ingestion layer only ever sees ``Iterator[RowChunk]``.  Today
that comes from ``pandas.read_csv(chunksize=...)``; tomorrow it can come from a
Parquet scanner or a ``COPY``-fed database cursor, and nothing downstream
changes.  That indirection is the whole reason this module exists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

import pandas as pd

from app.core.enums import DatasetKind
from app.core.errors import ErrorCode, IngestionError

#: Read everything as object dtype. Pandas' type inference is the enemy here:
#: it turns IDs into floats and amounts into unpredictable numerics. We do our
#: own typed parsing in `normalizer`, where errors are attributable to a row.
_READ_KWARGS: dict[str, Any] = {
    "dtype": str,
    "keep_default_na": False,
    "na_values": [],
    "skipinitialspace": True,
}


@dataclass(slots=True)
class RowChunk:
    """A slice of a source file, with the absolute row offset preserved.

    ``start_row`` is 1-based and counts the header, so ``start_row + i`` is the
    line number an operator will see in Excel.
    """

    rows: list[dict[str, Any]]
    start_row: int
    headers: list[str]

    def __len__(self) -> int:
        return len(self.rows)


class ChunkReader(Protocol):
    """Anything that can stream a source as chunks of dict rows."""

    headers: list[str]

    def chunks(self) -> Iterator[RowChunk]: ...


class CsvChunkReader:
    """Streams a CSV file in fixed-size chunks."""

    def __init__(self, path: Path, *, chunk_size: int = 10_000, encoding: str = "utf-8") -> None:
        self.path = Path(path)
        self.chunk_size = chunk_size
        self.encoding = encoding
        self.headers = self._read_headers()

    def _read_headers(self) -> list[str]:
        if not self.path.exists():
            raise IngestionError(
                f"File not found: {self.path.name}",
                code=ErrorCode.UNREADABLE_FILE,
                context={"path": str(self.path)},
            )
        if self.path.stat().st_size == 0:
            raise IngestionError(
                f"{self.path.name} is empty.",
                code=ErrorCode.EMPTY_FILE,
                context={"path": self.path.name},
            )
        try:
            head = pd.read_csv(self.path, nrows=0, encoding=self.encoding, **_READ_KWARGS)
        except UnicodeDecodeError:
            # Bank exports are frequently latin-1. Retry once, then give up.
            self.encoding = "latin-1"
            head = pd.read_csv(self.path, nrows=0, encoding=self.encoding, **_READ_KWARGS)
        except pd.errors.EmptyDataError as exc:
            raise IngestionError(
                f"{self.path.name} contains no parsable columns.",
                code=ErrorCode.EMPTY_FILE,
            ) from exc
        except pd.errors.ParserError as exc:
            raise IngestionError(
                f"{self.path.name} is not valid CSV: {exc}",
                code=ErrorCode.UNREADABLE_FILE,
            ) from exc
        return [str(c) for c in head.columns]

    def chunks(self) -> Iterator[RowChunk]:
        offset = 2  # line 1 is the header
        try:
            reader = pd.read_csv(
                self.path,
                chunksize=self.chunk_size,
                encoding=self.encoding,
                **_READ_KWARGS,
            )
            for frame in reader:
                rows = frame.to_dict("records")
                yield RowChunk(rows=rows, start_row=offset, headers=self.headers)
                offset += len(rows)
        except pd.errors.ParserError as exc:
            raise IngestionError(
                f"{self.path.name} failed to parse at approximately line {offset}: {exc}",
                code=ErrorCode.UNREADABLE_FILE,
                context={"approxLine": offset},
            ) from exc


class InMemoryChunkReader:
    """Adapter for already-materialised rows -- used by tests and benchmarks."""

    def __init__(self, rows: list[dict[str, Any]], *, chunk_size: int = 10_000) -> None:
        self._rows = rows
        self.chunk_size = chunk_size
        self.headers = list(rows[0].keys()) if rows else []

    def chunks(self) -> Iterator[RowChunk]:
        for start in range(0, len(self._rows), self.chunk_size):
            yield RowChunk(
                rows=self._rows[start : start + self.chunk_size],
                start_row=start + 2,
                headers=self.headers,
            )


def validate_upload(filename: str, size: int, allowed: set[str], max_bytes: int) -> str:
    """Filename/extension/size gate.  Content is never executed or evaluated."""
    suffix = Path(filename).suffix.lower()
    if suffix not in allowed:
        raise IngestionError(
            f"Unsupported file type '{suffix or filename}'. Expected: {', '.join(sorted(allowed))}.",
            code=ErrorCode.INVALID_FILE_TYPE,
            context={"filename": filename, "allowed": sorted(allowed)},
        )
    if size > max_bytes:
        raise IngestionError(
            f"{filename} is {size / 1e6:.1f} MB, above the {max_bytes / 1e6:.0f} MB limit.",
            code=ErrorCode.FILE_TOO_LARGE,
            context={"filename": filename, "size": size, "maxBytes": max_bytes},
        )
    if size == 0:
        raise IngestionError(
            f"{filename} is empty.", code=ErrorCode.EMPTY_FILE, context={"filename": filename}
        )
    return suffix


def checksum_file(path: Path, *, block: int = 1 << 20) -> str:
    """Streaming SHA-256 -- never loads the file into memory to hash it."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for piece in iter(lambda: fh.read(block), b""):
            digest.update(piece)
    return f"sha256:{digest.hexdigest()}"


def reader_for(path: Path, kind: DatasetKind, chunk_size: int) -> ChunkReader:
    """Factory -- the single place that decides how a source is read."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return CsvChunkReader(path, chunk_size=chunk_size)
    raise IngestionError(
        f"No reader registered for '{suffix}' ({kind.value}).",
        code=ErrorCode.INVALID_FILE_TYPE,
    )
