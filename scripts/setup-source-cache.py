#!/usr/bin/env python3
"""Set up the spokenform-gold external source cache on a new machine.

Clones (or updates) the three upstream repositories at the exact revisions
pinned in ``sources/manifest.json`` and verifies that the expected upstream
files are present.

Usage
-----
    python scripts/setup-source-cache.py [--cache-root PATH] [--work-root PATH]

Defaults::

    cache-root  ../spokenform-gold-source-cache   (next to the repo checkout)
    work-root   ../spokenform-gold-work            (next to the repo checkout)

After the script finishes, the repository-root ``config.toml`` points at
the default sibling cache and work directories, so production commands can
run without path flags. The environment variables below remain optional
overrides for custom locations::

    export SPOKENFORM_GOLD_SOURCE_CACHE="$(cd ../spokenform-gold-source-cache && pwd)"
    export SPOKENFORM_GOLD_WORK="$(cd ../spokenform-gold-work && pwd)"

Requirements
------------
- git >= 2.20 (for ``git clone --depth`` + ``git checkout``)
- Python >= 3.10 (standard library only)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

# ── Pinned source definitions ────────────────────────────────────────────────
# Each entry mirrors the relevant fields from sources/manifest.json and
# sources/source-lock.json.  Update these when the manifest is re-pinned.

MANIFEST_PATH = Path(__file__).resolve().parent.parent / "sources" / "manifest.json"


@dataclass(frozen=True)
class UpstreamSource:
    """One upstream repository to clone into the source cache."""

    name: str
    clone_url: str
    revision: str
    # Paths that must exist inside the cloned checkout after ``git checkout``.
    expected_paths: tuple[str, ...] = ()
    # Whether this is a Hugging Face Space (needs special clone handling).
    is_hf_space: bool = False
    # Extra notes shown during verification.
    notes: str = ""


SOURCES: list[UpstreamSource] = [
    UpstreamSource(
        name="async_tn",
        clone_url="https://huggingface.co/spaces/async-vocie-ai/text-to-speech-normalization-benchmark",
        revision="ad8fa8152279bb13c0ded87e3d465494c319da30",
        expected_paths=(
            "data/sentences.json",
            "data/multilingual-sentences.json",
        ),
        is_hf_space=True,
        notes="Hugging Face Space — may require `huggingface-cli login` if private.",
    ),
    UpstreamSource(
        name="polynorm",
        clone_url="https://github.com/apple/ml-speech-polynorm-bench",
        revision="f3c67e047bea6b7c40bc2466c0fdaad51d8ce67d",
        expected_paths=(
            # We only check that the directory exists; glob expansion happens
            # at ingestion time.
            "polynorm_bench",
        ),
    ),
    UpstreamSource(
        name="proteno",
        clone_url="https://github.com/amazon-science/proteno",
        revision="8839501abaf50eeccbe21a2397cefa118eae9660",
        expected_paths=(
            "data/English/unnorm_list.pkl",
            "data/English/norm_list.pkl",
            "data/Spanish/unnorm_list.pkl",
            "data/Spanish/norm_list.pkl",
        ),
    ),
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(
    cmd: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess with sensible defaults."""
    return subprocess.run(
        cmd,
        cwd=cwd,
        check=check,
        text=True,
        capture_output=capture,
    )


def git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run a git command."""
    return run(("git", *args), cwd=cwd, capture=True)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def clone_or_update(source: UpstreamSource, cache_root: Path) -> Path:
    """Clone the repo (shallow) or fetch + checkout if it already exists."""
    dest = cache_root / source.name

    if (dest / ".git").is_dir():
        print(f"  Repository already exists at {dest}")
        print(f"  Fetching revision {source.revision[:12]}…")
        git("fetch", "--depth", "1", "origin", source.revision, cwd=dest)
        git("checkout", source.revision, cwd=dest)
        print(f"  ✓ Checked out {source.revision[:12]}")
        return dest

    print(f"  Cloning {source.clone_url} → {dest}")
    # Shallow clone at the exact commit when possible.
    try:
        git(
            "clone",
            "--depth", "1",
            "--single-branch",
            f"--branch={source.revision}",
            source.clone_url,
            str(dest),
        )
    except subprocess.CalledProcessError:
        # Some hosts (HF Spaces) don't allow shallow clone by arbitrary SHA.
        # Fall back to a full clone + checkout.
        print("  Shallow clone by SHA failed; falling back to full clone…")
        if dest.exists():
            shutil.rmtree(dest)
        git("clone", source.clone_url, str(dest))
        git("checkout", source.revision, cwd=dest)

    print(f"  ✓ Cloned and checked out {source.revision[:12]}")
    return dest


def verify_source(source: UpstreamSource, checkout: Path) -> list[str]:
    """Return a list of missing expected paths (empty = all good)."""
    missing: list[str] = []
    for rel in source.expected_paths:
        # Support simple glob patterns (one ``*`` segment).
        if "*" in rel:
            matches = list(checkout.glob(rel))
            if not matches:
                missing.append(rel)
        else:
            if not (checkout / rel).exists():
                missing.append(rel)
    return missing


def load_manifest_revisions(repo_root: Path) -> dict[str, str]:
    """Load the pinned revisions from sources/manifest.json for cross-check."""
    manifest_path = repo_root / "sources" / "manifest.json"
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    revisions: dict[str, str] = {}
    for src in data.get("sources", []):
        name = src.get("name", "")
        rev = src.get("revision", "")
        if name and rev and name in {s.name for s in SOURCES}:
            revisions[name] = rev
    return revisions


def create_work_dir(work_root: Path) -> None:
    """Create the disposable work directory with expected subdirectories."""
    ensure_dir(work_root)
    for sub in ("reports", "reviews", "promotion_staging", "canonical-next",
                "review_batches", "census"):
        ensure_dir(work_root / sub)
    print(f"  ✓ Work directory ready at {work_root}")


# ── Main ─────────────────────────────────────────────────────────────────────

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Set up the spokenform-gold external source cache.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    repo_root = Path(__file__).resolve().parent.parent
    default_cache = repo_root.parent / "spokenform-gold-source-cache"
    default_work = repo_root.parent / "spokenform-gold-work"

    parser.add_argument(
        "--cache-root",
        type=Path,
        default=default_cache,
        help=f"Where to clone upstream repos (default: {default_cache})",
    )
    parser.add_argument(
        "--work-root",
        type=Path,
        default=default_work,
        help=f"Disposable work directory (default: {default_work})",
    )
    parser.add_argument(
        "--skip-work-dir",
        action="store_true",
        help="Don't create the work directory.",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing checkouts; don't clone or fetch.",
    )
    args = parser.parse_args(argv)

    cache_root: Path = args.cache_root.resolve()
    work_root: Path = args.work_root.resolve()

    # ── Cross-check with manifest ────────────────────────────────────────
    manifest_revs = load_manifest_revisions(repo_root)
    if manifest_revs:
        print("Cross-checking with sources/manifest.json …")
        for src in SOURCES:
            mrev = manifest_revs.get(src.name)
            if mrev and mrev != src.revision:
                print(
                    f"  ⚠ {src.name}: script revision {src.revision[:12]} "
                    f"≠ manifest revision {mrev[:12]}"
                )
                print("    Update this script or re-pin the manifest.")
        print()

    # ── Clone / verify each source ───────────────────────────────────────
    ensure_dir(cache_root)
    all_ok = True

    for src in SOURCES:
        print(f"── {src.name} {'─' * (60 - len(src.name))}")
        if src.notes:
            print(f"  Note: {src.notes}")

        if args.verify_only:
            checkout = cache_root / src.name
            if not checkout.is_dir():
                print(f"  ✗ Directory not found: {checkout}")
                all_ok = False
                continue
        else:
            checkout = clone_or_update(src, cache_root)

        # Verify revision
        actual_rev = git("rev-parse", "HEAD", cwd=checkout).stdout.strip()
        if actual_rev != src.revision:
            print(
                f"  ⚠ HEAD is {actual_rev[:12]}, expected {src.revision[:12]}"
            )
            if not args.verify_only:
                print("  Attempting checkout…")
                git("checkout", src.revision, cwd=checkout)
                actual_rev = git("rev-parse", "HEAD", cwd=checkout).stdout.strip()
                if actual_rev != src.revision:
                    print("  ✗ Could not reach pinned revision")
                    all_ok = False
        else:
            print(f"  ✓ Revision {src.revision[:12]}")

        # Verify expected files
        missing = verify_source(src, checkout)
        if missing:
            print("  ✗ Missing expected paths:")
            for p in missing:
                print(f"      {p}")
            all_ok = False
        else:
            print("  ✓ All expected paths present")

        print()

    # ── Work directory ───────────────────────────────────────────────────
    if not args.skip_work_dir:
        print("── work directory ──")
        create_work_dir(work_root)
        print()

    # ── Summary ──────────────────────────────────────────────────────────
    print("=" * 64)
    if all_ok:
        print("✓ Source cache is ready.")
    else:
        print("⚠ Source cache has issues — see warnings above.")
        print("  Some issues may be expected (e.g. HF Space auth).")

    print()
    print("The repository config.toml points at these default sibling paths.")
    print("Use the following only as overrides when custom paths are needed:")
    print(f'  export SPOKENFORM_GOLD_SOURCE_CACHE="{cache_root}"')
    print(f'  export SPOKENFORM_GOLD_WORK="{work_root}"')
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
