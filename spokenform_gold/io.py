from __future__ import annotations

import glob
import hashlib
import json
from pathlib import Path
from typing import Any
from collections.abc import Iterable


def expand_jsonl_paths(paths: Iterable[str | Path]) -> list[Path]:
    expanded: set[Path] = set()
    for raw in paths:
        value = str(raw)
        if any(char in value for char in "*?[]"):
            matches = [Path(item) for item in glob.glob(value, recursive=True)]
        else:
            path = Path(value)
            if path.is_dir():
                matches = sorted(path.rglob("*.jsonl"))
            else:
                matches = [path]
        for match in matches:
            if match.suffix == ".jsonl" and match.exists():
                expanded.add(match.resolve())
    return sorted(expanded)


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, payload: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def read_jsonl(path: str | Path) -> list[dict]:
    records = []
    source = Path(path)
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{source}:{line_number}: invalid JSON: {exc}"
                ) from exc
            if not isinstance(payload, dict):
                raise ValueError(f"{source}:{line_number}: expected JSON object")
            payload["_source_line"] = line_number
            payload["_source_file"] = str(source)
            records.append(payload)
    return records


def read_records(paths: Iterable[str | Path]) -> list[dict]:
    records: list[dict] = []
    for path in expand_jsonl_paths(paths):
        records.extend(read_jsonl(path))
    return records


def write_jsonl(path: str | Path, records: Iterable[dict]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            clean = {
                key: value for key, value in record.items() if not key.startswith("_")
            }
            handle.write(json.dumps(clean, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
