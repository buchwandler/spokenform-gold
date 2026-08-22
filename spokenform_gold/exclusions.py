from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from .io import read_json

_SHAPE_RULES = (
    ("ipv4", re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")),
    ("date", re.compile(r"^\d{1,4}[/-]\d{1,2}[/-]\d{1,4}$")),
    ("time", re.compile(r"^\d{1,2}:\d{2}")),
    ("decimal", re.compile(r"^-?\d[\d,]*\.\d+$")),
    ("fraction", re.compile(r"^\d+/\d+$")),
    ("version", re.compile(r"^v?\d+(?:\.\d+)+")),
    ("letters_digits", re.compile(r"^[A-Za-z]+[A-Za-z0-9-]*\d[A-Za-z0-9-]*$")),
    ("digits", re.compile(r"^\d+$")),
)


def infer_surface_shape(value: object) -> str:
    text = str(value or "").strip()
    for name, pattern in _SHAPE_RULES:
        if pattern.search(text):
            return name
    if text and text.isupper():
        return "uppercase"
    if text and text.isalpha():
        return "letters"
    if text:
        return "mixed"
    return "unknown"


def _source_for_path(path: str | Path) -> str:
    name = Path(path).stem
    for suffix in ("_exclusions", ".exclusions"):
        name = name.removesuffix(suffix)
    return name


def load_exclusions(paths: Iterable[str | Path]) -> list[dict]:
    items: list[dict] = []
    for path in paths:
        payload = read_json(path)
        if not isinstance(payload, list):
            raise TypeError(f"exclusion file must contain a list: {path}")
        source = _source_for_path(path)
        for item in payload:
            if not isinstance(item, dict):
                raise TypeError(f"exclusion entries must be objects: {path}")
            copied = dict(item)
            copied.setdefault("source", source)
            items.append(copied)
    return items


def build_exclusion_analysis(exclusions: Iterable[dict]) -> dict:
    rows = []
    for item in exclusions:
        source_category = (
            item.get("source_category") or item.get("category") or "unknown"
        )
        language = item.get("language") or "unknown"
        surface = item.get("surface") or item.get("detail", "")
        rows.append(
            {
                "source": item.get("source", "unknown"),
                "reason": item.get("reason", "unknown"),
                "source_category": str(source_category),
                "language": str(language),
                "surface_shape": item.get("surface_shape")
                or infer_surface_shape(surface),
            }
        )

    counts = Counter(
        (
            row["source"],
            row["reason"],
            row["source_category"],
            row["language"],
            row["surface_shape"],
        )
        for row in rows
    )
    groups = [
        {
            "source": source,
            "reason": reason,
            "source_category": category,
            "language": language,
            "surface_shape": shape,
            "count": count,
        }
        for (source, reason, category, language, shape), count in sorted(counts.items())
    ]
    return {
        "exclusions": len(rows),
        "sources": dict(sorted(Counter(row["source"] for row in rows).items())),
        "reasons": dict(sorted(Counter(row["reason"] for row in rows).items())),
        "groups": groups,
    }
