#!/usr/bin/env python3
"""Set up the pinned Spokenform Gold external source cache."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from spokenform_gold.source_cache import (
    ensure_source,
    load_source_definitions,
    verify_source,
)


def create_work_dir(work_root: Path) -> None:
    work_root.mkdir(parents=True, exist_ok=True)
    for name in (
        "reports",
        "reviews",
        "promotion_staging",
        "canonical-next",
        "review_batches",
        "census",
    ):
        (work_root / name).mkdir(exist_ok=True)


def main(argv: Sequence[str] | None = None) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=repo_root.parent / "spokenform-gold-source-cache",
    )
    parser.add_argument(
        "--work-root", type=Path, default=repo_root.parent / "spokenform-gold-work"
    )
    parser.add_argument("--skip-work-dir", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--accept-upstream-licenses", action="store_true")
    args = parser.parse_args(argv)

    definitions = load_source_definitions(repo_root)
    cache_root = args.cache_root.resolve()
    for definition in definitions:
        print(f"-- {definition.name}@{definition.revision}")
        if args.verify_only:
            verify_source(definition, definition.path(cache_root))
        else:
            checkout = ensure_source(
                definition,
                cache_root,
                accept_upstream_licenses=args.accept_upstream_licenses,
            )
            print(f"   ready: {checkout}")
    if not args.skip_work_dir:
        create_work_dir(args.work_root.resolve())
    print(f"Source cache is ready: {cache_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
