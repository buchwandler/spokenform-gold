#!/usr/bin/env python3
"""Plan the next Spokenform Gold benchmark release version."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

INITIAL_BASE_VERSION = (0, 0, 0)
_VERSION_RE = re.compile(
    r"^(?P<prefix>v)?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<kind>exp|candidate)(?:\.(?P<number>[1-9]\d*))?)?$"
)
_VERSION_LIKE_RE = re.compile(r"^v?\d+(?:\.\d+){1,}(?:[-+].*)?$")


class VersionPlanningError(ValueError):
    """Raised when release tags cannot be safely interpreted."""


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> Version:
        match = _VERSION_RE.fullmatch(value.removeprefix("v"))
        if match is None or match.group("kind") is not None:
            raise ValueError(f"not a stable benchmark version: {value!r}")
        return cls(*(int(match.group(name)) for name in ("major", "minor", "patch")))

    def bump(self, kind: str) -> Version:
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            return Version(self.major, self.minor, self.patch + 1)
        raise VersionPlanningError(f"unsupported version bump: {kind!r}")

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class ParsedTag:
    tag: str
    base: Version
    maturity: str | None
    number: int | None


def parse_tag(tag: str) -> ParsedTag | None:
    """Parse one benchmark tag, ignoring unrelated tags."""
    if not isinstance(tag, str) or not tag:
        return None
    if not _VERSION_LIKE_RE.fullmatch(tag):
        return None
    match = _VERSION_RE.fullmatch(tag)
    if match is None:
        raise VersionPlanningError(f"malformed benchmark release tag: {tag!r}")
    base = Version(
        int(match.group("major")),
        int(match.group("minor")),
        int(match.group("patch")),
    )
    raw_kind = match.group("kind")
    kind = {"exp": "experimental", "candidate": "candidate"}.get(raw_kind)
    return ParsedTag(
        tag=tag,
        base=base,
        maturity=kind,
        number=int(match.group("number"))
        if match.group("number")
        else (0 if kind else None),
    )


def parse_tags(tags: Iterable[str]) -> tuple[ParsedTag, ...]:
    parsed: list[ParsedTag] = []
    for tag in tags:
        item = parse_tag(tag.strip())
        if item is not None:
            parsed.append(item)
    return tuple(parsed)


def _target_tag_is_available(
    parsed: tuple[ParsedTag, ...], target: Version, maturity: str
) -> bool:
    if maturity != "stable":
        return True
    return not any(item.maturity is None and item.base == target for item in parsed)


def next_release_version(
    tags: Iterable[str], *, bump: str, maturity: str
) -> dict[str, object]:
    """Return the next release identity without mutating Git tags."""
    if bump not in {"major", "minor", "patch"}:
        raise VersionPlanningError(f"unsupported version bump: {bump!r}")
    if maturity not in {"experimental", "candidate", "stable"}:
        raise VersionPlanningError(f"unsupported release maturity: {maturity!r}")

    parsed = parse_tags(tags)
    stable_bases = [item.base for item in parsed if item.maturity is None]
    current_base = max(stable_bases, default=Version(*INITIAL_BASE_VERSION))
    target = current_base.bump(bump)

    if maturity == "stable":
        version = str(target)
        tag = f"v{version}"
        if not _target_tag_is_available(parsed, target, maturity):
            raise VersionPlanningError(f"benchmark release tag already exists: {tag}")
        prerelease = False
    else:
        numbers = [
            item.number or 0
            for item in parsed
            if item.base == target and item.maturity == maturity
        ]
        number = max(numbers, default=0) + 1
        version = f"{target}-{('exp' if maturity == 'experimental' else 'candidate')}.{number}"
        tag = f"v{version}"
        prerelease = True

    return {
        "base_version": str(target),
        "version": version,
        "tag": tag,
        "maturity": maturity,
        "prerelease": prerelease,
    }


def git_tags() -> tuple[str, ...]:
    completed = subprocess.run(
        ("git", "tag", "--list"), check=True, capture_output=True, text=True
    )
    return tuple(line for line in completed.stdout.splitlines() if line.strip())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--tags-from-git", action="store_true")
    source.add_argument("--tags-file", type=Path)
    source.add_argument("--tag", action="append", dest="tags")
    parser.add_argument("--bump", required=True, choices=("patch", "minor", "major"))
    parser.add_argument(
        "--maturity", required=True, choices=("experimental", "candidate", "stable")
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the complete plan as JSON."
    )
    parser.add_argument(
        "--field", choices=("base_version", "version", "tag", "maturity", "prerelease")
    )
    parser.add_argument("--github-output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.tags_from_git:
        tags = git_tags()
    elif args.tags_file is not None:
        tags = tuple(args.tags_file.read_text(encoding="utf-8").splitlines())
    else:
        tags = tuple(args.tags or ())
    result = next_release_version(tags, bump=args.bump, maturity=args.maturity)

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as handle:
            for key, value in result.items():
                rendered = str(value).lower() if isinstance(value, bool) else str(value)
                handle.write(f"{key}={rendered}\n")
    if args.field:
        print(result[args.field])
    elif args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["version"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
