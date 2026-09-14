from __future__ import annotations

import json
import pickle
from pathlib import Path

import pytest

from spokenform_gold.corpus import exact_surface_hash
from spokenform_gold.release_sources import ReleaseSourceLoader
from spokenform_gold.source_resolver import resolve_release_record


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    release = tmp_path / "release"
    release_sources = release / "sources"
    release_sources.mkdir(parents=True)
    entries = [
        {
            "name": "async_tn",
            "kind": "upstream",
            "materialization_policy": "review_required",
            "source_url": "https://example.invalid/async",
            "revision": "async-rev",
            "license": "Apache-2.0",
            "upstream_files": [
                {"path": "data/sentences.json"},
                {"path": "data/multilingual-sentences.json"},
            ],
        },
        {
            "name": "polynorm",
            "kind": "projection_cache",
            "materialization_policy": "external_ref_only",
            "source_url": "https://example.invalid/poly",
            "revision": "poly-rev",
            "license": "CC BY-NC-ND 4.0",
            "upstream_files": [{"path": "polynorm_bench/*/*_groundtruth.jsonl"}],
        },
        {
            "name": "proteno_en",
            "parent_source": "proteno",
            "kind": "upstream",
            "materialization_policy": "review_required",
            "source_url": "https://example.invalid/proteno",
            "revision": "proteno-rev",
            "license": "CC BY-SA 3.0 Unported",
            "upstream_files": [{"path": "data/English/unnorm_list.pkl"}],
        },
    ]
    (release_sources / "manifest.json").write_text(
        json.dumps({"version": "test", "sources": entries}), encoding="utf-8"
    )
    cache = tmp_path / "cache"
    checkouts = {
        "async_tn": cache / "async",
        "polynorm": cache / "poly",
        "proteno": cache / "proteno",
    }
    async_root = checkouts["async_tn"]
    (async_root / "data").mkdir(parents=True)
    (async_root / "data" / "sentences.json").write_text(
        json.dumps(
            [
                {
                    "row_id": 7,
                    "original_text": "Async input",
                    "normalized_text": "not Gold",
                }
            ]
        ),
        encoding="utf-8",
    )
    (async_root / "data" / "multilingual-sentences.json").write_text(
        json.dumps(
            [{"row_id": 8, "languages": {"de": {"original_text": "Mehrsprachig"}}}]
        ),
        encoding="utf-8",
    )
    poly_root = checkouts["polynorm"] / "polynorm_bench" / "de-DE"
    poly_root.mkdir(parents=True)
    (poly_root / "de-DE_groundtruth.jsonl").write_text(
        '{"index": 4, "original_text": "Poly input", "normalized_text": "not Gold"}\n',
        encoding="utf-8",
    )
    proteno_root = checkouts["proteno"] / "data" / "English"
    proteno_root.mkdir(parents=True)
    (proteno_root / "unnorm_list.pkl").write_bytes(pickle.dumps(["Proteno input"]))
    return release, cache


def _record(source: str, source_id: str, text: str) -> dict:
    return {
        "id": f"{source}-{source_id}",
        "materialization": "external_ref",
        "input": None,
        "external_ref": {
            "source": source,
            "source_id": source_id,
            "source_input_hash": exact_surface_hash(text),
        },
        "source": {"benchmark": source},
        "annotation": {"oracle": {"canonical_output": "Gold truth"}, "units": []},
    }


def test_loader_resolves_all_source_families_and_never_uses_expected_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, cache = _fixture(tmp_path)
    checkouts = {
        "async_tn": cache / "async",
        "polynorm": cache / "poly",
        "proteno": cache / "proteno",
    }
    monkeypatch.setattr(
        "spokenform_gold.release_sources.ensure_source",
        lambda definition, *_args, **_kwargs: checkouts[definition.name],
    )
    loader = ReleaseSourceLoader(
        release, cache, accepted_sources={"async_tn", "polynorm", "proteno_en"}
    )
    assert loader(_record("async_tn", "english:7", "Async input")) == "Async input"
    assert (
        loader(
            _record("async_tn", "multilingual:8", "Mehrsprachig") | {"language": "de"}
        )
        == "Mehrsprachig"
    )
    assert loader(_record("polynorm", "de-DE:4", "Poly input")) == "Poly input"
    assert (
        loader(_record("proteno_en", "proteno:en:1", "Proteno input"))
        == "Proteno input"
    )


def test_wrong_source_hash_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, cache = _fixture(tmp_path)
    monkeypatch.setattr(
        "spokenform_gold.release_sources.ensure_source",
        lambda definition, *_a, **_k: (
            cache
            / {"async_tn": "async", "polynorm": "poly", "proteno": "proteno"}[
                definition.name
            ]
        ),
    )
    record = _record("async_tn", "english:7", "wrong text")
    with pytest.raises(ValueError, match="source hash mismatch"):
        resolve_release_record(
            record, source_loader=ReleaseSourceLoader(release, cache)
        )


def test_embedded_records_do_not_require_source_cache(tmp_path: Path) -> None:
    release, cache = _fixture(tmp_path)
    record = {"materialization": "embedded", "input": "embedded text"}
    assert ReleaseSourceLoader(release, cache)(record) == "embedded text"


def test_wrong_revision_and_offline_cache_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release, cache = _fixture(tmp_path)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError("Offline source cache is missing or invalid")

    monkeypatch.setattr("spokenform_gold.release_sources.ensure_source", fail)
    loader = ReleaseSourceLoader(release, cache, offline=True)
    with pytest.raises(FileNotFoundError, match="Offline source cache"):
        loader(_record("async_tn", "english:7", "Async input"))
