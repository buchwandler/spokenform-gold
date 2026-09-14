#!/usr/bin/env python3
"""Compare a release candidate with an existing immutable Gold release."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

_IGNORED_METADATA_FIELDS = frozenset({"generated_at", "build_timestamp"})


def _manifest_source(value: str | Path) -> tuple[dict[str, Any], Path]:
    path = Path(value).resolve()
    manifest_path = path / "manifest.json" if path.is_dir() else path
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"release manifest must contain an object: {manifest_path}")
    return payload, manifest_path


def _checksum_map(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, separator, filename = line.partition("  ")
        if separator and digest and filename:
            values[filename] = digest
    return values


def compare_release_candidates(
    candidate: str | Path,
    existing: str | Path,
    *,
    candidate_checksums: str | Path | None = None,
    existing_checksums: str | Path | None = None,
) -> dict[str, Any]:
    """Compare semantic manifests and optional deterministic archive checksums."""
    candidate_manifest, candidate_path = _manifest_source(candidate)
    existing_manifest, existing_path = _manifest_source(existing)
    keys = sorted(
        (set(candidate_manifest) | set(existing_manifest)) - _IGNORED_METADATA_FIELDS
    )
    differences = {
        key: {
            "candidate": candidate_manifest.get(key),
            "existing": existing_manifest.get(key),
        }
        for key in keys
        if candidate_manifest.get(key) != existing_manifest.get(key)
    }
    if (candidate_checksums is None) != (existing_checksums is None):
        raise ValueError(
            "candidate and existing archive checksums must be supplied together"
        )
    if candidate_checksums is not None and existing_checksums is not None:
        candidate_hashes = _checksum_map(Path(candidate_checksums))
        existing_hashes = _checksum_map(Path(existing_checksums))
        if candidate_hashes != existing_hashes:
            differences["archive_sha256"] = {
                "candidate": candidate_hashes,
                "existing": existing_hashes,
            }
    return {
        "equivalent": not differences,
        "differences": differences,
        "candidate_manifest": str(candidate_path),
        "existing_manifest": str(existing_path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("existing", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--candidate-checksums", type=Path)
    parser.add_argument("--existing-checksums", type=Path)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = compare_release_candidates(
        args.candidate,
        args.existing,
        candidate_checksums=args.candidate_checksums,
        existing_checksums=args.existing_checksums,
    )
    print(
        json.dumps(result, indent=2, sort_keys=True)
        if args.json
        else ("equivalent" if result["equivalent"] else "different")
    )
    return 0 if result["equivalent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
