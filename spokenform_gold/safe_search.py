"""Bounded repository search for coding-agent inspection."""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path

DEFAULT_MAX_MATCHES = 100
DEFAULT_MAX_CHARS_PER_LINE = 500
DEFAULT_MAX_OUTPUT = 20_000
_SOURCE_DIRECTORIES = {
    "spokenform_gold",
    "tests",
    "docs",
    "templates",
    "schemas",
    "taxonomy",
    "scripts",
}
_SOURCE_FILES = {"AGENTS.md", "README.md", "pyproject.toml"}
_EXCLUDED_DIRECTORIES = {
    ".git",
    ".ledger",
    ".taskledger",
    ".venv",
    "__pycache__",
    "data",
    "reports",
}


def _is_excluded(path: Path, excluded_roots: tuple[Path, ...]) -> bool:
    if any(path == root or root in path.parents for root in excluded_roots):
        return True
    return any(
        part.startswith("context_spokenform_gold") or part.endswith(".index.json")
        for part in path.parts
    )


def _iter_files(
    root: Path, *, include_data: bool, excluded_roots: tuple[Path, ...]
) -> Iterable[Path]:
    root = root.resolve()
    if root.is_file():
        if not _is_excluded(root, excluded_roots):
            yield root
        return
    if not root.is_dir():
        return
    allowed = set(_SOURCE_DIRECTORIES)
    if include_data:
        allowed.add("data")
    for name in sorted(_SOURCE_FILES):
        path = root / name
        if path.is_file() and not _is_excluded(path, excluded_roots):
            yield path
    for directory in sorted(allowed):
        path = root / directory
        if not path.is_dir() or _is_excluded(path, excluded_roots):
            continue
        for current, directories, files in os.walk(path):
            current_path = Path(current)
            directories[:] = sorted(
                name
                for name in directories
                if name not in _EXCLUDED_DIRECTORIES
                and not name.startswith("context_spokenform_gold")
                and not name.endswith(".index.json")
                and not _is_excluded(current_path / name, excluded_roots)
            )
            for name in sorted(files):
                candidate = current_path / name
                if not _is_excluded(candidate, excluded_roots):
                    yield candidate


def search_text(
    pattern: str,
    *,
    root: str | Path = ".",
    include_data: bool = False,
    literal: bool = False,
    max_matches: int = DEFAULT_MAX_MATCHES,
    max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
    max_output: int = DEFAULT_MAX_OUTPUT,
    excluded_roots: Iterable[str | Path] = (),
) -> str:
    """Search source-oriented text and return a deterministically bounded result."""

    if max_matches <= 0 or max_chars_per_line <= 0 or max_output <= 0:
        raise ValueError("search limits must be positive")
    expression = re.compile(re.escape(pattern) if literal else pattern)
    root_path = Path(root).resolve()
    exclusions = tuple(Path(path).expanduser().resolve() for path in excluded_roots)
    matches = 0
    output: list[str] = []
    output_size = 0
    for path in _iter_files(
        root_path, include_data=include_data, excluded_roots=exclusions
    ):
        if matches >= max_matches or output_size >= max_output:
            break
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(text.splitlines(), 1):
            if not expression.search(line):
                continue
            matches += 1
            rendered = line[:max_chars_per_line]
            result = f"{path.relative_to(root_path)}:{line_number}:{rendered}\n"
            remaining = max_output - output_size
            output.append(result[:remaining])
            output_size += min(len(result), remaining)
            if matches >= max_matches or output_size >= max_output:
                break
    return "".join(output)
