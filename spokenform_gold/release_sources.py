"""Hydrate external references from a verified Gold release source manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .importers.proteno import _load_payload
from .source_cache import ensure_source, load_source_definitions


class ReleaseSourceLoader:
    """Resolve public release source references to verified input text."""

    def __init__(
        self,
        release_root: str | Path,
        cache_dir: str | Path,
        *,
        offline: bool = False,
        refresh: bool = False,
        accepted_sources: set[str] | None = None,
    ) -> None:
        self.release_root = Path(release_root).resolve()
        self.cache_dir = Path(cache_dir).resolve()
        self.offline = offline
        self.refresh = refresh
        self.accepted_sources = accepted_sources
        manifest_path = self.release_root / "sources" / "manifest.json"
        self.source_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self._definitions = {
            name: definition
            for definition in load_source_definitions(self.release_root)
            for name in definition.source_names
        }

    def __call__(self, record: dict[str, Any]) -> str:
        if record.get("materialization") != "external_ref":
            value = record.get("input")
            if not isinstance(value, str):
                raise ValueError("embedded release record has no input text")
            return value
        reference = record.get("external_ref")
        if not isinstance(reference, dict):
            raise TypeError("external_ref record is missing external_ref metadata")
        source_name = reference.get("source") or (record.get("source") or {}).get(
            "benchmark"
        )
        source_id = reference.get("source_id")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("external_ref record is missing source name")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("external_ref record is missing source_id")
        if (
            self.accepted_sources is not None
            and source_name not in self.accepted_sources
        ):
            raise PermissionError(
                f"upstream source {source_name} was not explicitly accepted"
            )
        definition = self._definitions.get(source_name)
        if definition is None:
            raise ValueError(
                f"source {source_name!r} is not present in the release manifest"
            )
        checkout = ensure_source(
            definition,
            self.cache_dir,
            offline=self.offline,
            refresh=self.refresh,
            accept_upstream_licenses=self.accepted_sources is not None,
        )
        if source_name == "async_tn":
            return self._async_text(checkout, source_id, record)
        if source_name == "polynorm":
            return self._polynorm_text(checkout, source_id)
        if source_name.startswith("proteno") or source_name == "proteno":
            return self._proteno_text(checkout, source_name, source_id)
        raise ValueError(f"unsupported external Gold source: {source_name}")

    @staticmethod
    def _async_text(checkout: Path, source_id: str, record: dict[str, Any]) -> str:
        parts = source_id.split(":")
        if not parts or parts[0] not in {"english", "multilingual"}:
            raise ValueError(f"invalid Async TN source_id: {source_id}")
        suite = parts[0]
        relative = (
            "data/sentences.json"
            if suite == "english"
            else "data/multilingual-sentences.json"
        )
        payload = json.loads((checkout / relative).read_text(encoding="utf-8"))
        wanted = ":".join(parts[1:])
        language = str(record.get("language", ""))
        for position, row in enumerate(payload, 1):
            if not isinstance(row, dict):
                continue
            row_id = next(
                (
                    row.get(key)
                    for key in ("row_id", "sentence_id", "id", "row_index", "index")
                    if row.get(key) is not None
                ),
                position,
            )
            if suite == "english":
                if str(row_id) == wanted:
                    return _require_text(row.get("original_text"), source_id)
                continue
            if str(row_id) != wanted:
                continue
            languages = row.get("languages")
            if not isinstance(languages, dict):
                break
            localized = languages.get(language) or languages.get(
                _language_code(language)
            )
            if isinstance(localized, dict):
                return _require_text(localized.get("original_text"), source_id)
        raise KeyError(f"Async TN source row not found: {source_id}")

    @staticmethod
    def _polynorm_text(checkout: Path, source_id: str) -> str:
        locale, separator, index = source_id.partition(":")
        if not separator or not locale or not index:
            raise ValueError(f"invalid PolyNorm source_id: {source_id}")
        path = checkout / "polynorm_bench" / locale / f"{locale}_groundtruth.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"PolyNorm locale source is missing: {path}")
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict) and str(row.get("index")) == index:
                    return _require_text(row.get("original_text"), source_id)
        raise KeyError(f"PolyNorm source row not found: {source_id}")

    @staticmethod
    def _proteno_text(checkout: Path, source_name: str, source_id: str) -> str:
        parts = source_id.split(":")
        if len(parts) != 3 or parts[0] != "proteno":
            raise ValueError(f"invalid Proteno source_id: {source_id}")
        language, index_text = parts[1], parts[2]
        directories = {"en": "English", "es": "Spanish", "ta": "Tamil"}
        directory = directories.get(language)
        if directory is None:
            raise ValueError(f"unsupported Proteno language: {language}")
        try:
            index = int(index_text)
        except ValueError as exc:
            raise ValueError(f"invalid Proteno source index: {source_id}") from exc
        if index < 1:
            raise ValueError(f"invalid Proteno source index: {source_id}")
        payload = _load_payload(checkout / "data" / directory / "unnorm_list.pkl")
        if not isinstance(payload, (list, tuple)) or index > len(payload):
            raise KeyError(f"Proteno source row not found: {source_id}")
        return _require_text(_text_value(payload[index - 1]), source_id)


def _language_code(value: str) -> str:
    return value.split("-", 1)[0].split("_", 1)[0]


def _text_value(value: object) -> object:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)) and all(
        isinstance(item, str) for item in value
    ):
        return " ".join(item for item in value if item)
    return value


def _require_text(value: object, source_id: str) -> str:
    text = _text_value(value)
    if not isinstance(text, str):
        raise TypeError(f"source row {source_id} does not contain input text")
    return text


def build_release_source_loader(
    release_root: str | Path,
    cache_dir: str | Path,
    *,
    offline: bool = False,
    refresh: bool = False,
    accept_upstream_licenses: bool = False,
) -> ReleaseSourceLoader:
    accepted_sources = None
    if accept_upstream_licenses:
        accepted_sources = {
            name
            for definition in load_source_definitions(release_root)
            for name in definition.source_names
        }
    return ReleaseSourceLoader(
        release_root,
        cache_dir,
        offline=offline,
        refresh=refresh,
        accepted_sources=accepted_sources,
    )


__all__ = ["ReleaseSourceLoader", "build_release_source_loader"]
