from __future__ import annotations

from pathlib import Path

from spokenform_gold.io import read_json, read_records, sha256_file


def load_release_manifest(gold_root: str | Path) -> dict:
    root = Path(gold_root)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing release manifest: {manifest_path}")
    return read_json(manifest_path)


def verify_release(gold_root: str | Path) -> dict:
    root = Path(gold_root)
    manifest = load_release_manifest(root)
    file_hashes = manifest.get("file_hashes", {})
    if not isinstance(file_hashes, dict) or not file_hashes:
        raise ValueError("release manifest is missing file hashes")
    for relative_path, expected_hash in sorted(file_hashes.items()):
        target = root / relative_path
        if not target.exists():
            raise ValueError(f"release file missing: {relative_path}")
        actual_hash = sha256_file(target)
        if actual_hash != expected_hash:
            raise ValueError(
                f"release hash mismatch for {relative_path}: expected {expected_hash} got {actual_hash}"
            )
    manifest_hash = sha256_file(root / "manifest.json")
    return {"manifest": manifest, "manifest_hash": manifest_hash}


def load_release_records(
    gold_root: str | Path,
    *,
    split: str | None = None,
    language: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    status: str | None = None,
    case_ids: set[str] | None = None,
) -> tuple[dict, list[dict]]:
    verification = verify_release(gold_root)
    root = Path(gold_root)
    records = read_records([root / "data"])
    filtered: list[dict] = []
    for record in records:
        if split and record.get("split") != split:
            continue
        if language and record.get("language") != language:
            continue
        if locale and record.get("locale") != locale:
            continue
        if status and record.get("status") != status:
            continue
        if case_ids and record.get("id") not in case_ids:
            continue
        if category and category not in {
            unit.get("category") for unit in record.get("units", [])
        }:
            continue
        filtered.append(record)
    filtered.sort(key=lambda record: record.get("id", ""))
    return verification["manifest"] | {
        "manifest_hash": verification["manifest_hash"]
    }, filtered
