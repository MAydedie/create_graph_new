from __future__ import annotations

import gzip
import hashlib
import io
import json
import pickle
import zipfile
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class FormalDataError(RuntimeError):
    def __init__(self, message: str, *, code: str, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.evidence = dict(evidence or {})

    def as_error(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "evidence": dict(self.evidence)}


class MissingDataError(FormalDataError):
    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, code="missing", evidence=evidence)


class MalformedDataError(FormalDataError):
    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, code="malformed", evidence=evidence)


class UnsupportedDataError(FormalDataError):
    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, code="unsupported", evidence=evidence)


class PartialDataError(FormalDataError):
    def __init__(self, message: str, *, evidence: Mapping[str, Any] | None = None) -> None:
        super().__init__(message, code="partial", evidence=evidence)


@dataclass(frozen=True)
class Inspection:
    dataset: str
    path: str
    status: str
    counts: dict[str, int] = field(default_factory=dict)
    fields: dict[str, list[str]] = field(default_factory=dict)
    gold: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset": self.dataset,
            "path": self.path,
            "status": self.status,
            "counts": _sorted_counts(self.counts),
            "fields": {key: sorted(values) for key, values in sorted(self.fields.items())},
            "gold": _stable(self.gold),
            "readiness": _stable(self.readiness),
            "errors": list(self.errors),
        }


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, set):
        return sorted(str(item) for item in value)
    if isinstance(value, list):
        return [_stable(item) for item in value]
    return value


def _sorted_counts(counts: Mapping[str, int]) -> dict[str, int]:
    return {key: int(counts[key]) for key in sorted(counts)}


def ok_inspection(
    dataset: str,
    path: Path,
    *,
    counts: Mapping[str, int] | None = None,
    fields: Mapping[str, Iterable[str]] | None = None,
    gold: Mapping[str, Any] | None = None,
    readiness: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return Inspection(
        dataset=dataset,
        path=str(path),
        status="ok",
        counts=dict(counts or {}),
        fields={key: sorted(str(item) for item in values) for key, values in (fields or {}).items()},
        gold=dict(gold or {}),
        readiness=dict(readiness or {}),
        errors=[],
    ).to_dict()


def error_inspection(dataset: str, path: Path, exc: FormalDataError) -> dict[str, Any]:
    return Inspection(dataset=dataset, path=str(path), status=exc.code, errors=[exc.as_error()]).to_dict()


def validate_inspector(dataset: str, path: str | Path, inspector: Callable[[Path], dict[str, Any]]) -> dict[str, Any]:
    path_obj = Path(path)
    try:
        return inspector(path_obj)
    except FormalDataError as exc:
        return error_inspection(dataset, path_obj, exc)


def ensure_file(path: Path) -> None:
    if not path.exists():
        raise MissingDataError(f"file does not exist: {path}", evidence={"path": str(path)})
    if not path.is_file():
        raise UnsupportedDataError(f"path is not a file: {path}", evidence={"path": str(path)})


def sha256_stream(path: Path, chunk_size: int = 1024 * 1024) -> str:
    ensure_file(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_object(path: Path) -> dict[str, Any]:
    ensure_file(path)
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise MalformedDataError(f"cannot parse JSON object: {exc}", evidence={"path": str(path)}) from exc
    if not isinstance(payload, dict):
        raise MalformedDataError("JSON payload must be an object", evidence={"path": str(path)})
    return payload


def iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    ensure_file(path)
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise MalformedDataError(
                        f"invalid JSONL at line {line_number}: {exc}",
                        evidence={"path": str(path), "line": line_number},
                    ) from exc
                if not isinstance(row, dict):
                    raise MalformedDataError(
                        f"JSONL row {line_number} must be an object",
                        evidence={"path": str(path), "line": line_number},
                    )
                yield line_number, row
    except OSError as exc:
        raise MalformedDataError(f"cannot read JSONL: {exc}", evidence={"path": str(path)}) from exc


def iter_zip_members(path: Path, suffixes: Sequence[str] | None = None) -> Iterator[tuple[str, bytes]]:
    ensure_file(path)
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith("/"):
                    continue
                if suffixes and not any(name.endswith(suffix) for suffix in suffixes):
                    continue
                yield name, archive.read(name)
    except zipfile.BadZipFile as exc:
        raise MalformedDataError(f"invalid ZIP archive: {exc}", evidence={"path": str(path)}) from exc


def iter_zip_jsonl_rows(path: Path, suffixes: Sequence[str]) -> Iterator[tuple[str, int, dict[str, Any]]]:
    ensure_file(path)
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith("/") or not any(name.endswith(suffix) for suffix in suffixes):
                    continue
                with archive.open(name, "r") as binary_handle:
                    text_handle = io.TextIOWrapper(binary_handle, encoding="utf-8")
                    for line_number, line in enumerate(text_handle, start=1):
                        if line.strip():
                            yield name, line_number, _parse_jsonl_row(line, name, line_number)
    except zipfile.BadZipFile as exc:
        raise MalformedDataError(f"invalid ZIP archive: {exc}", evidence={"path": str(path)}) from exc
    except UnicodeDecodeError as exc:
        raise MalformedDataError(f"invalid UTF-8 JSONL member: {exc}", evidence={"path": str(path)}) from exc


def iter_zip_gzip_jsonl_rows(path: Path, suffixes: Sequence[str]) -> Iterator[tuple[str, int, dict[str, Any]]]:
    ensure_file(path)
    try:
        with zipfile.ZipFile(path) as archive:
            for name in sorted(archive.namelist()):
                if name.endswith("/") or not any(name.endswith(suffix) for suffix in suffixes):
                    continue
                with archive.open(name, "r") as binary_handle:
                    with gzip.GzipFile(fileobj=binary_handle, mode="rb") as gzip_handle:
                        text_handle = io.TextIOWrapper(gzip_handle, encoding="utf-8")
                        for line_number, line in enumerate(text_handle, start=1):
                            if line.strip():
                                yield name, line_number, _parse_jsonl_row(line, name, line_number)
    except zipfile.BadZipFile as exc:
        raise MalformedDataError(f"invalid ZIP archive: {exc}", evidence={"path": str(path)}) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise MalformedDataError(f"invalid gzip JSONL member: {exc}", evidence={"path": str(path)}) from exc


def _parse_jsonl_row(line: str, source: str, line_number: int) -> dict[str, Any]:
    try:
        row = json.loads(line)
    except json.JSONDecodeError as exc:
        raise MalformedDataError(
            f"invalid JSONL in {source} at line {line_number}: {exc}",
            evidence={"source": source, "line": line_number},
        ) from exc
    if not isinstance(row, dict):
        raise MalformedDataError(
            f"JSONL row in {source} at line {line_number} must be an object",
            evidence={"source": source, "line": line_number},
        )
    return row


def iter_gzip_jsonl_bytes(member_name: str, payload: bytes) -> Iterator[tuple[int, dict[str, Any]]]:
    try:
        text = gzip.decompress(payload).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise MalformedDataError(f"invalid gzip JSONL member: {member_name}") from exc
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MalformedDataError(
                f"invalid JSONL in {member_name} at line {line_number}: {exc}",
                evidence={"member": member_name, "line": line_number},
            ) from exc
        if not isinstance(row, dict):
            raise MalformedDataError(
                f"JSONL row in {member_name} at line {line_number} must be an object",
                evidence={"member": member_name, "line": line_number},
            )
        yield line_number, row


def load_trusted_gzip_pickle(path: Path) -> Any:
    ensure_file(path)
    try:
        with gzip.open(path, "rb") as handle:
            return pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, AttributeError, ImportError, IndexError) as exc:
        raise MalformedDataError(f"cannot inspect trusted gzip pickle: {exc}", evidence={"path": str(path)}) from exc


def parquet_metadata(path: Path) -> tuple[list[str], int, int]:
    ensure_file(path)
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(path)
        return list(parquet_file.schema_arrow.names), int(parquet_file.metadata.num_rows), int(parquet_file.metadata.num_row_groups)
    except ImportError as exc:
        raise UnsupportedDataError("pyarrow is required for parquet inspection", evidence={"path": str(path)}) from exc
    except Exception as exc:
        raise MalformedDataError(f"cannot inspect parquet metadata: {exc}", evidence={"path": str(path)}) from exc


def iter_parquet_rows(path: Path, columns: Sequence[str] | None = None, batch_size: int = 1024) -> Iterator[dict[str, Any]]:
    ensure_file(path)
    try:
        import pyarrow.parquet as pq

        parquet_file = pq.ParquetFile(path)
        for batch in parquet_file.iter_batches(batch_size=batch_size, columns=list(columns) if columns else None):
            for row in batch.to_pylist():
                if not isinstance(row, dict):
                    raise MalformedDataError("parquet row must convert to an object", evidence={"path": str(path)})
                yield row
    except ImportError as exc:
        raise UnsupportedDataError("pyarrow is required for parquet row iteration", evidence={"path": str(path)}) from exc
    except FormalDataError:
        raise
    except Exception as exc:
        raise MalformedDataError(f"cannot iterate parquet rows: {exc}", evidence={"path": str(path)}) from exc


def require_fields(row: Mapping[str, Any], required: Iterable[str], location: str) -> None:
    missing = sorted(field for field in required if _nested_get(row, field) is None)
    if missing:
        raise PartialDataError(f"missing required fields at {location}: {', '.join(missing)}", evidence={"missing": missing})


def _nested_get(row: Mapping[str, Any], field: str) -> Any:
    current: Any = row
    for part in field.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def collect_row_fields(row: Mapping[str, Any]) -> list[str]:
    fields: list[str] = []
    for key in sorted(row):
        value = row[key]
        fields.append(str(key))
        if isinstance(value, Mapping):
            for child in collect_row_fields(value):
                fields.append(f"{key}.{child}")
    return sorted(fields)


def first_present_row(rows: Iterable[tuple[int, dict[str, Any]]]) -> tuple[int, dict[str, Any]]:
    for item in rows:
        return item
    raise PartialDataError("dataset contains no inspectable rows")
