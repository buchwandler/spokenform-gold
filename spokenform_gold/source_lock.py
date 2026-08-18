from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import sha256_file
from .taxonomy import load_source_manifest, repo_root


def build_source_lock(manifest_path: str | Path | None = None) -> dict[str, Any]:
    """Build deterministic source metadata without copying source corpus text."""
    manifest = load_source_manifest(manifest_path)
    root = Path(manifest_path).resolve().parent.parent if manifest_path else repo_root()
    sources = []
    for entry in sorted(
        manifest.get("sources", []), key=lambda item: item.get("name", "")
    ):
        locked = {
            key: entry[key]
            for key in (
                "name",
                "revision",
                "source_url",
                "license",
                "license_id",
                "license_scope",
                "redistribution_status",
                "materialization_policy",
            )
            if key in entry
        }
        artifacts = []
        for artifact in sorted(
            entry.get("files", []), key=lambda item: item.get("path", "")
        ):
            item = dict(artifact)
            candidate = root / artifact.get("path", "")
            if candidate.is_file():
                item["observed_sha256"] = sha256_file(candidate)
            artifacts.append(item)
        locked["artifacts"] = artifacts
        locked["upstream_files"] = sorted(
            entry.get("upstream_files", []), key=lambda item: item.get("path", "")
        )
        sources.append(locked)
    return {
        "schema_version": "1.0.0",
        "manifest_version": manifest.get("version"),
        "sources": sources,
    }
