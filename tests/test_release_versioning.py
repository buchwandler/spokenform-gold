from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.next_release_version import (
    VersionPlanningError,
    main,
    next_release_version,
)


def test_no_tags_minor_experimental_starts_at_first_prerelease() -> None:
    assert (
        next_release_version([], bump="minor", maturity="experimental")["version"]
        == "0.1.0-exp.1"
    )


def test_patch_experimental_follows_stable_release() -> None:
    result = next_release_version(["v0.1.0"], bump="patch", maturity="experimental")
    assert result["version"] == "0.1.1-exp.1"


def test_prerelease_number_increments_for_same_target() -> None:
    tags = ["v0.1.0", "v0.1.1-exp.1"]
    result = next_release_version(tags, bump="patch", maturity="experimental")
    assert result["version"] == "0.1.1-exp.2"


def test_legacy_prerelease_counts_as_zero() -> None:
    result = next_release_version(
        ["v0.1.0", "0.1.1-exp"], bump="patch", maturity="experimental"
    )
    assert result["version"] == "0.1.1-exp.1"


def test_candidate_numbering_is_independent_from_experimental() -> None:
    tags = ["v0.1.0", "v0.1.1-exp.4", "v0.1.1-candidate.2"]
    result = next_release_version(tags, bump="patch", maturity="candidate")
    assert result["version"] == "0.1.1-candidate.3"


def test_stable_target_has_no_suffix() -> None:
    result = next_release_version(["v0.1.0"], bump="minor", maturity="stable")
    assert result == {
        "base_version": "0.2.0",
        "version": "0.2.0",
        "tag": "v0.2.0",
        "maturity": "stable",
        "prerelease": False,
    }


@pytest.mark.parametrize(
    ("bump", "version"),
    [("major", "2.0.0"), ("minor", "1.3.0"), ("patch", "1.2.4")],
)
def test_bump_ordering(bump: str, version: str) -> None:
    assert (
        next_release_version(["v1.2.3"], bump=bump, maturity="stable")["version"]
        == version
    )


def test_unrelated_tags_are_ignored() -> None:
    result = next_release_version(
        ["v0.1.0", "docs-v2", "release-2026", "foo"], bump="patch", maturity="stable"
    )
    assert result["version"] == "0.1.1"


@pytest.mark.parametrize(
    "tag", ["v0.1", "v0.1.0-beta", "v0.1.0-exp.0", "v0.1.0-exp.1.2"]
)
def test_malformed_benchmark_tags_fail(tag: str) -> None:
    with pytest.raises(VersionPlanningError, match="malformed"):
        next_release_version([tag], bump="patch", maturity="stable")


def test_existing_stable_target_is_rejected_by_target_check() -> None:
    from scripts.next_release_version import (
        ParsedTag,
        Version,
        _target_tag_is_available,
    )

    parsed = tuple(
        ParsedTag(tag=tag, base=Version.parse(tag), maturity=None, number=None)
        for tag in ("v0.1.0", "v0.1.1")
    )
    assert not _target_tag_is_available(parsed, Version(0, 1, 1), "stable")


def test_cli_json_and_github_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    tags = tmp_path / "tags.txt"
    tags.write_text("v0.1.0\nv0.1.1-exp\n", encoding="utf-8")
    output = tmp_path / "github-output"

    assert (
        main(
            [
                "--tags-file",
                str(tags),
                "--bump",
                "patch",
                "--maturity",
                "experimental",
                "--json",
                "--github-output",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["tag"] == "v0.1.1-exp.1"
    assert "prerelease=true" in output.read_text(encoding="utf-8")
