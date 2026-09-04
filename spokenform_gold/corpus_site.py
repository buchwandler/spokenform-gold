"""Deterministic, language-sharded public browser for canonical Gold records."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .html_report import _escape, _options, _record_row, source_names
from .review_lineage import sanitize_review_artifact
from .validation import validate_records

DEFAULT_ISSUES_URL = "https://github.com/buchwandler/spokenform-gold/issues/new"
DEFAULT_MAX_RECORDS_PER_PAGE = 3000


def _digest(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _file_hash(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _language_slug(language: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", language).strip("-")
    if not slug:
        raise ValueError(f"language cannot be represented as a site path: {language!r}")
    return slug


def _site_css() -> str:
    return ":root{font-family:system-ui,sans-serif;color:#17202a;background:#f5f7fa}body{margin:0}main{max-width:1600px;margin:auto;padding:1.5rem}header,.panel{background:#fff;border:1px solid #d8dee8;border-radius:.6rem;padding:1rem 1.25rem;margin-bottom:1rem}.muted,small{color:#657184}small{display:block}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.7rem}.kpi{background:#eef4ff;padding:.8rem;border-radius:.4rem}.kpi strong,.kpi span{display:block}.kpi strong{font-size:1.35rem}.filters{display:flex;flex-wrap:wrap;gap:.7rem;align-items:end}.filters label{display:flex;flex-direction:column;font-size:.9rem}.filters input,.filters select{padding:.45rem;min-width:9rem}.row-count{margin-left:auto;font-weight:600}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-top:.8rem}th,td{border:1px solid #d8dee8;padding:.5rem;text-align:left;vertical-align:top}th{background:#edf1f6}.record-row>td:last-child{min-width:32rem}details{margin-top:.5rem}summary{cursor:pointer;font-weight:600}.details-grid{display:grid;grid-template-columns:2fr 1fr;gap:1rem}.fields{margin:0}.field{display:grid;grid-template-columns:9rem 1fr;border-bottom:1px solid #edf0f4;padding:.3rem 0}.field dt{font-weight:600}.field dd{margin:0;white-space:pre-wrap;word-break:break-word}.row-actions{display:flex;gap:.3rem;flex-wrap:wrap}.row-actions button{padding:.3rem .45rem}.highlight{outline:4px solid #e0a400;outline-offset:3px}@media(max-width:800px){main{padding:.75rem}.details-grid{grid-template-columns:1fr}.record-row>td:last-child{min-width:20rem}}"


def _site_script(routing: Mapping[str, str] | None = None) -> str:
    route = json.dumps(
        dict(routing or {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return f"""const routing={route};
const buttons=[...document.querySelectorAll('[data-report-issue]')];
function norm(x){{return (x||'').toString().toLowerCase().trim()}}
const controls=[...document.querySelectorAll('[data-filter]')],rows=[...document.querySelectorAll('.record-row')],count=document.querySelector('#row-count');
function filter(){{let shown=0;rows.forEach(row=>{{const keep=controls.every(control=>{{const wanted=norm(control.value);if(!wanted)return true;const actual=norm(row.dataset[control.dataset.filter]);return control.dataset.filter==='search'?actual.includes(wanted):actual.split(' ').includes(wanted)}});row.hidden=!keep;if(keep)shown++}});if(count)count.textContent=`${{shown}} / ${{rows.length}}`}}
controls.forEach(x=>{{x.addEventListener('input',filter);x.addEventListener('change',filter)}});
function copy(value){{if(navigator.clipboard)navigator.clipboard.writeText(value)}}
document.querySelectorAll('[data-copy-id]').forEach(b=>b.addEventListener('click',()=>copy(b.dataset.copyId)));
document.querySelectorAll('[data-copy-link]').forEach(b=>b.addEventListener('click',()=>copy(location.href.split('#')[0]+'#record='+encodeURIComponent(b.dataset.copyLink))));
document.querySelectorAll('[data-copy-correction]').forEach(b=>b.addEventListener('click',()=>copy(b.dataset.copyCorrection)));
buttons.forEach(button=>button.addEventListener('click',()=>{{const row=button.closest('.record-row'),url=new URL(button.dataset.reportIssue,location.href),query=new URLSearchParams(url.search),id=row.dataset.recordId,page=location.href.split('#')[0]+'#record='+encodeURIComponent(id);const body=`## Spokenform Gold corpus report\n\nRecord ID: ${{id}}\nLanguage: ${{row.dataset.language}}\nLocale: ${{row.dataset.locale}}\nStatus: ${{row.dataset.status}}\n\nCorpus page:\n${{page}}\n\n### Current record\n\nInput:\n> ${{row.dataset.input}}\n\nCanonical:\n> ${{row.dataset.canonical}}\n\n### What looks wrong?\n\nPlease describe the issue here.`;query.set('title','[Corpus] Possible error in '+id);query.set('body',body);url.search=query;location.href=url.toString()}}));
function route(){{const id=decodeURIComponent(location.hash.replace(/^#(?:record=)?/,''));if(id&&routing[id]){{location.replace(routing[id]+'#record='+encodeURIComponent(id));return}}rows.forEach(row=>row.classList.remove('highlight'));if(!id)return;const row=document.getElementById('record-'+id);if(row){{row.classList.add('highlight');row.scrollIntoView();row.querySelectorAll('details').forEach(x=>x.open=true)}}}}
filter();route();window.addEventListener('hashchange',route);"""


def _page(title: str, content: str, script: str, back: str | None = None) -> str:
    link = f'<p><a href="{_escape(back)}">Back to all languages</a></p>' if back else ""
    return f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{_escape(title)}</title><style>{_site_css()}</style></head><body><main><header><h1>{_escape(title)}</h1>{link}</header>{content}<script>{script}</script></main></body></html>'


def _language_summary(records: list[dict]) -> dict[str, Any]:
    statuses = Counter(str(row.get("status", "unknown")) for row in records)
    categories = Counter(
        str(unit.get("category"))
        for row in records
        for unit in row.get("units", [])
        if isinstance(unit, dict) and unit.get("category")
    )
    sources = Counter(source for row in records for source in source_names(row))
    return {
        "records": len(records),
        "locales": sorted(
            {str(row.get("locale")) for row in records if row.get("locale")}
        ),
        "statuses": dict(sorted(statuses.items())),
        "categories": dict(sorted(categories.items())),
        "sources": dict(sorted(sources.items())),
    }


def _record_content(
    records: list[dict], evidence: Mapping[str, dict], issues_url: str | None
) -> str:
    languages = sorted(
        {str(row.get("language")) for row in records if row.get("language")}
    )
    locales = {str(row.get("locale")) for row in records if row.get("locale")}
    statuses = {str(row.get("status")) for row in records if row.get("status")}
    categories = {
        str(unit.get("category"))
        for row in records
        for unit in row.get("units", [])
        if isinstance(unit, dict) and unit.get("category")
    }
    sources = {source for row in records for source in source_names(row)}
    rows = "".join(
        _record_row(row, evidence.get(row.get("id")), issues_url)
        for row in sorted(records, key=lambda item: str(item.get("id", "")))
    )
    filters = f'<div class="filters"><label>Search<input type="search" data-filter="search" placeholder="ID, input, output…"></label><label>Locale<select data-filter="locale"><option value="">All</option>{_options(locales)}</select></label><label>Status<select data-filter="status"><option value="">All</option>{_options(statuses)}</select></label><label>Category<select data-filter="categories"><option value="">All</option>{_options(categories)}</select></label><label>Source<select data-filter="source"><option value="">All</option>{_options(sources)}</select></label><label>Provenance<select data-filter="provenance"><option value="">All</option><option value="native">native</option><option value="translation-derived">translation-derived</option></select></label><span class="row-count">Visible: <strong id="row-count"></strong></span></div>'
    return f'<section class="panel"><p>{len(records)} record(s) · {len(languages)} language(s)</p>{filters}<div class="table-scroll"><table><thead><tr><th>ID / family</th><th>Split / locale</th><th>Status</th><th>Categories</th><th>Record</th></tr></thead><tbody>{rows}</tbody></table></div></section>'


def render_corpus_site(
    records: Iterable[dict],
    *,
    review_evidence: Iterable[dict] = (),
    issues_url: str | None = DEFAULT_ISSUES_URL,
    max_records_per_page: int = DEFAULT_MAX_RECORDS_PER_PAGE,
) -> dict[str, str]:
    """Render all site files in memory after refusing invalid canonical records."""
    rows = sorted(
        (dict(row) for row in records), key=lambda row: str(row.get("id", ""))
    )
    errors = validate_records(rows)
    if errors:
        raise ValueError(
            "cannot generate corpus site for invalid corpus: " + "; ".join(errors)
        )
    if max_records_per_page <= 0:
        raise ValueError("max_records_per_page must be positive")
    evidence = {
        row.get("record_id"): sanitize_review_artifact(row)
        for row in review_evidence
        if isinstance(row, dict)
    }
    by_language: dict[str, list[dict]] = {}
    for row in rows:
        by_language.setdefault(str(row.get("language", "unknown")), []).append(row)
    files: dict[str, str] = {}
    language_manifest: dict[str, dict[str, Any]] = {}
    for language in sorted(by_language):
        language_rows = by_language[language]
        slug = _language_slug(language)
        summary = _language_summary(language_rows)
        if len(language_rows) <= max_records_per_page:
            path = f"{slug}.html"
            files[path] = _page(
                f"Spokenform Gold corpus — {language}",
                f'<p class="muted">{summary["records"]} records · {len(summary["locales"])} locale(s)</p>'
                + _record_content(language_rows, evidence, issues_url),
                _site_script(),
            )
            language_manifest[language] = {
                "records": len(language_rows),
                "file": path,
                "sha256": _file_hash(files[path]),
            }
        else:
            part_paths = []
            routing = {}
            for index in range(0, len(language_rows), max_records_per_page):
                part = index // max_records_per_page + 1
                path = f"{slug}/part-{part:03d}.html"
                chunk = language_rows[index : index + max_records_per_page]
                files[path] = _page(
                    f"Spokenform Gold corpus — {language} (part {part})",
                    _record_content(chunk, evidence, issues_url),
                    _site_script(),
                    "../index.html",
                )
                part_paths.append(path)
                for row in chunk:
                    routing[str(row["id"])] = f"part-{part:03d}.html"
            index_path = f"{slug}/index.html"
            part_links = "".join(
                f'<li><a href="{_escape(path.split("/")[-1])}">{_escape(path)}</a></li>'
                for path in part_paths
            )
            files[index_path] = _page(
                f"Spokenform Gold corpus — {language}",
                f'<p class="muted">{summary["records"]} records across {len(part_paths)} deterministic parts.</p><section class="panel"><p>Use a record deep link to route to its detail part.</p><ul>{part_links}</ul></section>',
                _site_script({key: value for key, value in routing.items()}),
                "../index.html",
            )
            language_manifest[language] = {
                "records": len(language_rows),
                "file": index_path,
                "parts": part_paths,
                "sha256": _file_hash(files[index_path]),
                "routing": f"{slug}/routing.json",
            }
            files[f"{slug}/routing.json"] = (
                json.dumps(routing, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
    status_counts = Counter(str(row.get("status", "unknown")) for row in rows)
    category_counts = Counter(
        str(unit.get("category"))
        for row in rows
        for unit in row.get("units", [])
        if isinstance(unit, dict) and unit.get("category")
    )
    source_counts = Counter(source for row in rows for source in source_names(row))
    language_rows = "".join(
        f'<tr><td><a href="{_escape(language_manifest[language]["file"])}">{_escape(language)}</a></td><td>{len(by_language[language])}</td><td>{_escape(", ".join(_language_summary(by_language[language])["locales"]))}</td><td>{_escape(json.dumps(_language_summary(by_language[language])["statuses"], sort_keys=True))}</td></tr>'
        for language in sorted(by_language)
    )
    index_content = f'<section class="panel"><div class="kpis"><div class="kpi"><strong>{len(rows)}</strong><span>Records</span></div><div class="kpi"><strong>{len({row.get("family_id") for row in rows})}</strong><span>Families</span></div><div class="kpi"><strong>{len(by_language)}</strong><span>Languages</span></div><div class="kpi"><strong>{len(status_counts)}</strong><span>Statuses</span></div></div><h2>Languages</h2><div class="table-scroll"><table><thead><tr><th>Language</th><th>Records</th><th>Locales</th><th>Status counts</th></tr></thead><tbody>{language_rows}</tbody></table></div><h2>Coverage summary</h2><pre>{_escape(json.dumps({"statuses": dict(sorted(status_counts.items())), "categories": dict(sorted(category_counts.items())), "sources": dict(sorted(source_counts.items()))}, ensure_ascii=False, indent=2, sort_keys=True))}</pre><p class="muted">Record IDs are permanent correction handles. Use Report issue on a record to include its ID and current deep link.</p></section>'
    files["index.html"] = _page("Spokenform Gold corpus", index_content, _site_script())
    corpus_rows = [
        {key: value for key, value in row.items() if not key.startswith("_")}
        for row in rows
    ]
    manifest = {
        "schema_version": "1",
        "generator": "spokenform-gold corpus-site",
        "corpus_hash": _digest(corpus_rows),
        "record_count": len(rows),
        "languages": {
            language: language_manifest[language]
            for language in sorted(language_manifest)
        },
    }
    files["manifest.json"] = (
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    return files


def generate_corpus_site(
    records: Iterable[dict],
    out_dir: str | Path,
    *,
    review_evidence: Iterable[dict] = (),
    issues_url: str | None = DEFAULT_ISSUES_URL,
    max_records_per_page: int = DEFAULT_MAX_RECORDS_PER_PAGE,
    write: bool = False,
    check: bool = False,
) -> dict[str, int | str]:
    """Generate, explicitly write, or check deterministic site files."""
    if write and check:
        raise ValueError("choose either write or check")
    rendered = render_corpus_site(
        records,
        review_evidence=review_evidence,
        issues_url=issues_url,
        max_records_per_page=max_records_per_page,
    )
    root = Path(out_dir)
    existing = (
        {
            str(path.relative_to(root)): path.read_text(encoding="utf-8")
            for path in root.rglob("*")
            if path.is_file()
        }
        if root.is_dir()
        else {}
    )
    expected = set(rendered)
    changed = sum(existing.get(path) != content for path, content in rendered.items())
    missing = len(expected - set(existing))
    extra = len(set(existing) - expected)
    if write:
        root.mkdir(parents=True, exist_ok=True)
        for path, content in rendered.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        for path in sorted(set(existing) - expected):
            (root / path).unlink()
    return {
        "corpus_site": "stale" if changed or missing or extra else "current",
        "changed": changed,
        "missing": missing,
        "extra": extra,
        "files": len(expected),
    }


__all__ = [
    "DEFAULT_ISSUES_URL",
    "DEFAULT_MAX_RECORDS_PER_PAGE",
    "generate_corpus_site",
    "render_corpus_site",
]
