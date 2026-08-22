"""Self-contained HTML browser for a Spokenform Gold release."""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path


def _escape(value: object) -> str:
    return html.escape(str(value), quote=True)


def _json(value: object) -> str:
    return _escape(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _options(values: set[str]) -> str:
    return "".join(
        f'<option value="{_escape(value)}">{_escape(value)}</option>'
        for value in sorted(values)
    )


def _record_row(record: dict) -> str:
    units = [unit for unit in record.get("units", []) if isinstance(unit, dict)]
    categories = sorted(
        {str(unit.get("category")) for unit in units if unit.get("category")}
    )
    oracle = record.get("oracle", {})
    source = record.get("source", {})
    accepted = oracle.get("accepted_outputs", [])
    rejected = oracle.get("rejected_outputs", [])
    unit_rows = "".join(
        "<tr>"
        f"<td>{_escape(unit.get('surface', ''))}</td>"
        f"<td>{_escape(unit.get('category', ''))}</td>"
        f"<td>{_escape(unit.get('canonical', ''))}</td>"
        f"<td><pre>{_json(unit.get('semantic', {}))}</pre></td>"
        f"<td>{_escape(unit.get('policy', ''))}</td>"
        "</tr>"
        for unit in units
    )
    details = (
        f"<details><summary>{len(units)} unit(s), provenance, and review</summary>"
        '<div class="details-grid">'
        "<section><h4>Units</h4>"
        '<div class="table-scroll"><table><thead><tr><th>Surface</th><th>Category</th>'
        "<th>Canonical</th><th>Semantic</th><th>Policy</th></tr></thead>"
        f"<tbody>{unit_rows}</tbody></table></div></section>"
        f"<section><h4>Source</h4><pre>{_json(source)}</pre>"
        f"<h4>Review</h4><pre>{_json(record.get('review', {}))}</pre></section>"
        "</div></details>"
    )
    attrs = {
        "split": record.get("split", ""),
        "language": record.get("language", ""),
        "locale": record.get("locale", ""),
        "status": record.get("status", ""),
        "categories": " ".join(categories),
        "source": source.get("benchmark", ""),
        "search": " ".join(
            str(value)
            for value in (
                record.get("id", ""),
                record.get("family_id", ""),
                record.get("input", ""),
                oracle.get("canonical_output", record.get("expected_output", "")),
                " ".join(categories),
            )
        ),
    }
    attr_text = " ".join(
        f'data-{key}="{_escape(value)}"' for key, value in attrs.items()
    )
    variants = ""
    if len(accepted) > 1 or rejected:
        variants = (
            "<details><summary>Variants</summary>"
            f"<strong>Accepted</strong><pre>{_json(accepted)}</pre>"
            f"<strong>Rejected</strong><pre>{_json(rejected)}</pre></details>"
        )
    return (
        f'<tr class="record-row" {attr_text}>'
        f"<td><strong>{_escape(record.get('id', ''))}</strong>"
        f"<small>{_escape(record.get('family_id', ''))}</small></td>"
        f"<td>{_escape(record.get('split', ''))}<small>{_escape(record.get('locale', ''))}</small></td>"
        f"<td>{_escape(record.get('status', ''))}</td>"
        f"<td>{_escape(', '.join(categories) or 'negative control')}</td>"
        f"<td><strong>Input</strong><div>{_escape(record.get('input', ''))}</div>"
        f"<strong>Canonical</strong><div>{_escape(oracle.get('canonical_output', record.get('expected_output', '')))}</div>"
        f"{variants}{details}</td>"
        "</tr>"
    )


def render_release_html(
    output: str | Path,
    *,
    version: str,
    maturity: str,
    records: list[dict],
    coverage: dict,
    control_coverage: dict,
    counts: dict,
) -> Path:
    """Write a deterministic, dependency-free browser for release records."""
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    languages = {
        str(record.get("language")) for record in records if record.get("language")
    }
    locales = {str(record.get("locale")) for record in records if record.get("locale")}
    statuses = {str(record.get("status")) for record in records if record.get("status")}
    splits = {str(record.get("split")) for record in records if record.get("split")}
    sources = {
        str(record.get("source", {}).get("benchmark"))
        for record in records
        if record.get("source", {}).get("benchmark")
    }
    categories = {
        str(unit.get("category"))
        for record in records
        for unit in record.get("units", [])
        if isinstance(unit, dict) and unit.get("category")
    }
    rows = "".join(
        _record_row(record) for record in sorted(records, key=lambda row: row["id"])
    )
    status_counts = Counter(str(record.get("status", "unknown")) for record in records)
    split_counts = Counter(str(record.get("split", "unknown")) for record in records)
    summary = {
        "version": version,
        "maturity": maturity,
        "counts": counts,
        "records_by_split": dict(sorted(split_counts.items())),
        "records_by_status": dict(sorted(status_counts.items())),
    }
    css = """
:root{color-scheme:light dark;font-family:system-ui,sans-serif}body{margin:0;background:#f5f7fa;color:#17202a}main{max-width:1600px;margin:auto;padding:2rem}header,.panel{background:#fff;border:1px solid #d8dee8;border-radius:.6rem;padding:1rem 1.25rem;margin-bottom:1rem}h1,h2,h3,h4{margin-top:0}.muted,small{color:#657184}small{display:block}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(145px,1fr));gap:.7rem}.kpi{background:#eef4ff;padding:.8rem;border-radius:.4rem}.kpi strong,.kpi span{display:block}.kpi strong{font-size:1.35rem}.tabs{display:flex;gap:.5rem;flex-wrap:wrap;margin-bottom:1rem}.tabs button{padding:.65rem 1rem;border:1px solid #b9c4d2;border-radius:.4rem;background:#eef2f7;cursor:pointer}.tabs button.active{background:#20334d;color:#fff}.tab{display:none}.tab.active{display:block}.filters{display:flex;flex-wrap:wrap;gap:.7rem;align-items:end}.filters label{display:flex;flex-direction:column;font-size:.9rem}.filters input,.filters select{padding:.45rem;min-width:9rem}.row-count{margin-left:auto;font-weight:600}.table-scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;margin-top:.8rem}th,td{border:1px solid #d8dee8;padding:.5rem;text-align:left;vertical-align:top}th{background:#edf1f6}.record-row>td:last-child{min-width:32rem}details{margin-top:.5rem}summary{cursor:pointer;font-weight:600}.details-grid{display:grid;grid-template-columns:2fr 1fr;gap:1rem}pre{white-space:pre-wrap;word-break:break-word;max-height:24rem;overflow:auto}@media(prefers-color-scheme:dark){body{background:#121820;color:#edf2f7}header,.panel{background:#1b2530}th{background:#293746}.kpi{background:#20334d}.tabs button{background:#1d2834;color:#edf2f7}.tabs button.active{background:#4b7bb1}}@media(max-width:800px){main{padding:.75rem}.details-grid{grid-template-columns:1fr}.record-row>td:last-child{min-width:20rem}}
"""
    script = """
const buttons=[...document.querySelectorAll('[data-tab]')],tabs=[...document.querySelectorAll('.tab')];
function activate(id){tabs.forEach(x=>x.classList.toggle('active',x.id===id));buttons.forEach(x=>x.classList.toggle('active',x.dataset.tab===id));}
buttons.forEach(x=>x.addEventListener('click',()=>activate(x.dataset.tab)));
const controls=[...document.querySelectorAll('[data-filter]')],rows=[...document.querySelectorAll('.record-row')],count=document.querySelector('#row-count');
function norm(x){return (x||'').toString().toLowerCase().trim();}
function filter(){let shown=0;rows.forEach(row=>{const keep=controls.every(control=>{const wanted=norm(control.value);if(!wanted)return true;const actual=norm(row.dataset[control.dataset.filter]);return control.dataset.filter==='search'?actual.includes(wanted):actual.split(' ').includes(wanted);});row.hidden=!keep;if(keep)shown++;});count.textContent=`${shown} / ${rows.length}`;}
controls.forEach(x=>{x.addEventListener('input',filter);x.addEventListener('change',filter);});filter();
"""
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Spokenform Gold {_escape(version)}</title><style>{css}</style></head><body><main>
<header><h1>Spokenform Gold {_escape(version)}</h1><p class="muted">Self-contained release record browser · maturity: {_escape(maturity)}</p></header>
<section class="panel"><div class="kpis"><div class="kpi"><strong>{len(records)}</strong><span>Records</span></div><div class="kpi"><strong>{counts.get("families", 0)}</strong><span>Families</span></div><div class="kpi"><strong>{len(languages)}</strong><span>Languages</span></div><div class="kpi"><strong>{len(categories)}</strong><span>Categories</span></div><div class="kpi"><strong>{len(coverage.get("gaps", []))}</strong><span>Coverage gaps</span></div></div></section>
<nav class="tabs"><button class="active" data-tab="records">Records</button><button data-tab="coverage">Coverage</button><button data-tab="metadata">Metadata</button></nav>
<section id="records" class="tab active panel"><h2>Release records</h2><div class="filters"><label>Search<input type="search" data-filter="search" placeholder="ID, input, output…"></label><label>Split<select data-filter="split"><option value="">All</option>{_options(splits)}</select></label><label>Language<select data-filter="language"><option value="">All</option>{_options(languages)}</select></label><label>Locale<select data-filter="locale"><option value="">All</option>{_options(locales)}</select></label><label>Status<select data-filter="status"><option value="">All</option>{_options(statuses)}</select></label><label>Category<select data-filter="categories"><option value="">All</option>{_options(categories)}</select></label><label>Source<select data-filter="source"><option value="">All</option>{_options(sources)}</select></label><span class="row-count">Visible: <strong id="row-count"></strong></span></div><div class="table-scroll"><table><thead><tr><th>ID / family</th><th>Split / locale</th><th>Status</th><th>Categories</th><th>Record</th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section id="coverage" class="tab panel"><h2>Coverage</h2><h3>Canonical corpus</h3><pre>{_json(coverage)}</pre><h3>Control suites</h3><pre>{_json(control_coverage)}</pre></section>
<section id="metadata" class="tab panel"><h2>Release metadata</h2><pre>{_json(summary)}</pre></section>
<script>{script}</script></main></body></html>"""
    output_path.write_text(document, encoding="utf-8")
    return output_path


__all__ = ["render_release_html"]
