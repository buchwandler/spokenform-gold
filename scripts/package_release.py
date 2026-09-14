#!/usr/bin/env python3
"""Create deterministic archives and transport metadata for a Gold release."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import tarfile
import zipfile
from collections.abc import Iterable
from gzip import GzipFile
from pathlib import Path
from typing import Any

_EPOCH = 0
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _release_files(root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda p: p.relative_to(root).as_posix(),
        )
    )


def _archive_name(root: Path, path: Path) -> str:
    return f"{root.name}/{path.relative_to(root).as_posix()}"


def _stable_mode(path: Path) -> int:
    return 0o755 if path.is_dir() else 0o644


def _write_tar(root: Path, destination: Path) -> None:
    files = _release_files(root)
    with (
        destination.open("wb") as raw,
        GzipFile(fileobj=raw, mode="wb", filename="", mtime=_EPOCH) as compressed,
        tarfile.open(
            fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT
        ) as archive,
    ):
        directories = sorted(
            {path.parent for path in files if path.parent != root},
            key=lambda p: p.relative_to(root).as_posix(),
        )
        for directory in directories:
            info = tarfile.TarInfo(_archive_name(root, directory) + "/")
            info.type = tarfile.DIRTYPE
            info.mode = 0o755
            info.mtime = _EPOCH
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info)
        for path in files:
            info = tarfile.TarInfo(_archive_name(root, path))
            payload = path.read_bytes()
            info.size = len(payload)
            info.mode = _stable_mode(path)
            info.mtime = _EPOCH
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(payload))


def _write_zip(root: Path, destination: Path) -> None:
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in _release_files(root):
            name = _archive_name(root, path)
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (_stable_mode(path) | 0o100000) << 16
            archive.writestr(info, path.read_bytes())


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_release(
    release_root: str | Path, output_dir: str | Path | None = None
) -> dict[str, Any]:
    """Build deterministic release archives and return their transport metadata."""
    root = Path(release_root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"release root does not exist: {root}")
    if not (root / "manifest.json").is_file():
        raise FileNotFoundError(
            f"release manifest does not exist: {root / 'manifest.json'}"
        )
    destination = Path(output_dir).resolve() if output_dir is not None else root.parent
    destination.mkdir(parents=True, exist_ok=True)
    name = root.name
    tar_path = destination / f"{name}.tar.gz"
    zip_path = destination / f"{name}.zip"
    sums_path = destination / f"{name}-archive-SHA256SUMS"
    _write_tar(root, tar_path)
    _write_zip(root, zip_path)
    checksums = {tar_path.name: sha256(tar_path), zip_path.name: sha256(zip_path)}
    sums_path.write_text(
        "".join(
            f"{digest}  {filename}\n" for filename, digest in sorted(checksums.items())
        ),
        encoding="utf-8",
    )

    version = _release_version(root)
    manifest_asset = destination / f"{name}-manifest.json"
    sums_asset = destination / f"{name}-SHA256SUMS"
    shutil.copyfile(root / "manifest.json", manifest_asset)
    sums_asset.write_text(
        "".join(
            f"{digest}  {filename}\n" for filename, digest in sorted(checksums.items())
        )
        + f"{sha256(root / 'manifest.json')}  manifest.json\n",
        encoding="utf-8",
    )
    return {
        "release_root": str(root),
        "name": name,
        "version": version,
        "tar": str(tar_path),
        "zip": str(zip_path),
        "archive_checksums": str(sums_path),
        "manifest": str(manifest_asset),
        "checksums": str(sums_asset),
        "archive_sha256": checksums,
        "manifest_sha256": sha256(root / "manifest.json"),
    }


def _release_version(root: Path) -> str:
    payload = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    version = payload.get("benchmark_version")
    if not isinstance(version, str) or not version:
        raise ValueError(
            "release manifest benchmark_version must be a non-empty string"
        )
    return version


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release_root", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = package_release(args.release_root, args.output_dir)
    print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["tar"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
