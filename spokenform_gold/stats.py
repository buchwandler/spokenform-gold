from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from pathlib import Path


def build_stats(records: Iterable[dict], files: Iterable[str | Path]) -> dict:
    record_list = list(records)
    file_list = [str(Path(path)) for path in files]
    statuses = Counter()
    languages = Counter()
    locales = Counter()
    sources = Counter()
    splits = Counter()
    family_ids = set()

    for record in record_list:
        statuses[record.get("status")] += 1
        languages[record.get("language")] += 1
        locales[record.get("locale")] += 1
        sources[record.get("source", {}).get("benchmark")] += 1
        splits[record.get("split")] += 1
        if record.get("family_id"):
            family_ids.add(record["family_id"])

    return {
        "files": sorted(file_list),
        "file_count": len(file_list),
        "records": len(record_list),
        "families": len(family_ids),
        "statuses": dict(sorted(statuses.items())),
        "languages": dict(sorted(languages.items())),
        "locales": dict(sorted(locales.items())),
        "sources": dict(sorted(sources.items())),
        "splits": dict(sorted(splits.items())),
    }
