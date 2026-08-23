"""Dependency-free human-facing review/adjudication report HTML."""

from __future__ import annotations

import html
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .review import sentence_oracle_id
from .review_lineage import sanitize_review_artifact


def _escape(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _text(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return ", ".join(_text(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(f"{key}: {_text(value[key])}" for key in sorted(value))
    return str(value)


def _safe(value: Any) -> Any:
    return sanitize_review_artifact(value)


def _field(label: str, value: object) -> str:
    return f'<div class="field"><dt>{_escape(label)}</dt><dd>{_escape(_text(value))}</dd></div>'


def _units(units: object) -> str:
    if not isinstance(units, list) or not units:
        return '<p class="muted">No normalization units.</p>'
    rows = []
    for unit in units:
        if not isinstance(unit, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{_escape(unit.get('surface'))}</td>"
            f"<td>{_escape(unit.get('category'))}</td>"
            f"<td>{_escape(unit.get('canonical'))}</td>"
            f"<td>{_escape(_text(unit.get('semantic')))}</td>"
            f"<td>{_escape(unit.get('policy'))}</td>"
            "</tr>"
        )
    return (
        '<div class="table-scroll"><table class="units"><thead><tr>'
        "<th>Surface</th><th>Category</th><th>Canonical</th><th>Semantic</th><th>Policy</th>"
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _annotation_panel(title: str, row: dict | None) -> str:
    if not isinstance(row, dict):
        return f'<section class="reviewer"><h4>{_escape(title)}</h4><p class="muted">Evidence unavailable.</p></section>'
    annotation = row.get("annotation") or {}
    oracle = annotation.get("oracle") or {}
    return (
        f'<section class="reviewer"><h4>{_escape(title)}</h4>'
        '<dl class="fields">'
        + _field("Reviewer ID", row.get("reviewer_id"))
        + _field("Status", (row.get("review") or {}).get("status"))
        + _field("Canonical output", oracle.get("canonical_output"))
        + _field("Accepted outputs", oracle.get("accepted_outputs"))
        + _field("Rejected outputs", oracle.get("rejected_outputs"))
        + _field("Semantic interpretation", [unit.get("semantic") for unit in annotation.get("units", []) if isinstance(unit, dict)])
        + _field("Policy", [unit.get("policy") for unit in annotation.get("units", []) if isinstance(unit, dict)])
        + _field("Notes / rationale", annotation.get("notes"))
        + '</dl><h5>Units</h5>'
        + _units(annotation.get("units"))
        + "</section>"
    )


def _comparison_panel(comparison: dict | None) -> str:
    if not isinstance(comparison, dict):
        return '<section><h4>Comparison</h4><p class="muted">Comparison unavailable.</p></section>'
    dimensions = comparison.get("dimensions") or {}
    rows = []
    for key in sorted(dimensions):
        state = "DIFFERENT" if dimensions[key] else "SAME"
        rows.append(
            f'<tr class="{state.casefold()}"><th>{_escape(key)}</th><td>{state}</td></tr>'
        )
    return (
        '<section><h4>Comparison</h4>'
        f'<p class="comparison-state">{_escape(comparison.get("state", ""))}</p>'
        '<div class="table-scroll"><table><thead><tr><th>Dimension</th><th>Result</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></section>"
    )


def _adjudicator_panel(decisions: list[dict]) -> str:
    if not decisions:
        return '<section><h4>Adjudicator</h4><p class="muted">No decision artifact.</p></section>'
    rows = []
    for decision in decisions:
        oracle = decision.get("oracle") or {}
        rows.append(
            '<article class="decision">'
            '<dl class="fields">'
            + _field("Adjudicator ID", decision.get("adjudicator"))
            + _field("Final decision", decision.get("decision"))
            + _field("Final canonical output", oracle.get("canonical_output"))
            + _field("Accepted outputs", oracle.get("accepted_outputs"))
            + _field("Rejected outputs", oracle.get("rejected_outputs"))
            + _field("Family", decision.get("family_id"))
            + _field("License disposition", decision.get("license_disposition"))
            + _field("Source error codes", decision.get("source_error_codes"))
            + _field("Blocker", decision.get("blocker_code"))
            + _field("Blocker reason", decision.get("blocker_reason"))
            + _field("Attempted resolution", decision.get("attempted_resolution"))
            + _field("Rationale", decision.get("notes"))
            + "</dl></article>"
        )
    return f'<section><h4>Adjudicator</h4>{"".join(rows)}</section>'


def _critic_panel(decisions: list[dict]) -> str:
    values = []
    for decision in decisions:
        critic = decision.get("critic")
        status = decision.get("critic_status")
        if critic is not None:
            values.append(critic.get("status") if isinstance(critic, dict) else critic)
        elif status:
            values.append(status)
    if not values:
        return '<section><h4>Critic</h4><p class="muted">Not run.</p></section>'
    return f'<section><h4>Critic</h4><p class="critic">{_escape(_text(values))}</p></section>'


def _option_values(rows: list[dict], key: str) -> list[str]:
    values = set()
    for row in rows:
        value = row.get(key, "")
        if isinstance(value, str) and value:
            values.add(value)
        elif isinstance(value, list):
            values.update(str(item) for item in value if item)
    return sorted(values)


def _options(values: Iterable[str]) -> str:
    return "".join(f'<option value="{_escape(value)}">{_escape(value)}</option>' for value in values)


def _cluster_rows(
    candidates: list[dict],
    review_a: list[dict],
    review_b: list[dict],
    comparisons: list[dict],
    decisions: list[dict],
) -> list[dict]:
    a_map = {row.get("sentence_oracle_id"): row for row in review_a}
    b_map = {row.get("sentence_oracle_id"): row for row in review_b}
    comparison_map = {row.get("sentence_oracle_id"): row for row in comparisons}
    decision_by_candidate = {}
    for decision in decisions:
        decision_by_candidate.setdefault(decision.get("candidate_id"), []).append(decision)
    candidate_groups: dict[str, list[dict]] = {}
    for candidate in candidates:
        candidate_groups.setdefault(sentence_oracle_id(candidate), []).append(candidate)
    oracle_ids = set(candidate_groups) | set(comparison_map) | set(a_map) | set(b_map)
    rows = []
    for oracle_id in sorted(oracle_ids):
        members = candidate_groups.get(oracle_id, [])
        member_decisions = [
            decision
            for candidate in members
            for decision in decision_by_candidate.get(candidate.get("id"), [])
        ]
        if not member_decisions:
            member_decisions = [decision for decision in decisions if decision.get("sentence_oracle_id") == oracle_id]
        primary = next((item for item in member_decisions if item.get("record_id")), member_decisions[0] if member_decisions else {})
        review = a_map.get(oracle_id) or b_map.get(oracle_id) or {}
        annotation = review.get("annotation") or {}
        oracle = annotation.get("oracle") or {}
        final_oracle = primary.get("oracle") or {}
        sources = sorted({candidate.get("source", {}).get("benchmark", "") for candidate in members if candidate.get("source", {}).get("benchmark")})
        categories = sorted({unit.get("category", "") for candidate in members for unit in candidate.get("units", []) if isinstance(unit, dict) and unit.get("category")})
        if not categories:
            categories = sorted({unit.get("category", "") for unit in annotation.get("units", []) if isinstance(unit, dict) and unit.get("category")})
        disagreement = comparison_map.get(oracle_id, {}).get("disagreement", False)
        dimensions = comparison_map.get(oracle_id, {}).get("dimensions", {})
        rows.append({
            "oracle_id": oracle_id,
            "record_id": primary.get("record_id") or primary.get("represented_by_record_id") or "unassigned",
            "candidate_ids": sorted(candidate.get("id", "") for candidate in members if candidate.get("id")),
            "input": review.get("input") or (members[0].get("input") if members else ""),
            "canonical": final_oracle.get("canonical_output") or oracle.get("canonical_output"),
            "status": primary.get("status") or annotation.get("status", "unreviewed"),
            "decision": primary.get("decision", "pending"),
            "language": review.get("language") or (members[0].get("language") if members else ""),
            "locale": review.get("locale") or (members[0].get("locale") if members else ""),
            "categories": categories,
            "sources": sources,
            "agreement": "disagreement" if disagreement else "agreement",
            "dimensions": [key for key, changed in sorted(dimensions.items()) if changed],
            "blocker": primary.get("blocker_code", ""),
            "critic": primary.get("critic_status") or (primary.get("critic") or {}).get("status", "") if isinstance(primary.get("critic"), dict) else primary.get("critic", ""),
            "review_a": a_map.get(oracle_id),
            "review_b": b_map.get(oracle_id),
            "comparison": comparison_map.get(oracle_id),
            "decisions": member_decisions,
        })
    return rows


def render_review_html(
    output: str | Path,
    *,
    candidates: Iterable[dict],
    review_a: Iterable[dict],
    review_b: Iterable[dict],
    comparisons: Iterable[dict],
    decisions: Iterable[dict],
    validation: dict | None = None,
    batch_id: str | None = None,
) -> Path:
    candidate_rows = list(candidates)
    rows = _cluster_rows(candidate_rows, list(review_a), list(review_b), list(comparisons), list(decisions))
    decision_counts = Counter(row["decision"] for row in rows)
    agreement = sum(row["agreement"] == "agreement" for row in rows)
    disagreement = len(rows) - agreement
    unresolved = sum(row["decision"] in {"needs_review", "quarantine", "pending"} for row in rows)
    validation = validation or {"ready": True}
    kpis = [
        ("Candidates", len(candidate_rows)),
        ("Sentence clusters", len(rows)),
        ("A/B agreement", agreement),
        ("A/B disagreement", disagreement),
        ("Adjudicated", len(rows) - sum(row["decision"] == "pending" for row in rows)),
        ("Promote curated", decision_counts.get("promote_curated", 0)),
        ("Promote upstream", decision_counts.get("promote_upstream", 0)),
        ("Keep external", decision_counts.get("keep_external", 0)),
        ("Reject", decision_counts.get("reject", 0)),
        ("Quarantine", decision_counts.get("quarantine", 0)),
        ("Needs review", decision_counts.get("needs_review", 0)),
        ("Unresolved", unresolved),
        ("Validation", "READY" if validation.get("ready") else "BLOCKED"),
    ]
    filters = [
        ("decision", "Decision", _option_values(rows, "decision")),
        ("status", "Status", _option_values(rows, "status")),
        ("language", "Language", _option_values(rows, "language")),
        ("locale", "Locale", _option_values(rows, "locale")),
        ("categories", "Category", _option_values(rows, "categories")),
        ("sources", "Source", _option_values(rows, "sources")),
        ("agreement", "A/B agreement", _option_values(rows, "agreement")),
        ("dimensions", "Disagreement dimension", sorted({item for row in rows for item in row["dimensions"]})),
        ("blocker", "Blocker code", _option_values(rows, "blocker")),
        ("critic", "Critic", _option_values(rows, "critic")),
    ]
    filter_html = ''.join(
        f'<label>{_escape(label)}<select data-filter="{_escape(key)}"><option value="">All</option>{_options(values)}</select></label>'
        for key, label, values in filters
    )
    cards = []
    for row in rows:
        anchor_id = f"record-{row['record_id']}" if row["record_id"] != "unassigned" else f"cluster-{row['oracle_id']}"
        attrs = {
            "record": row["record_id"],
            "candidate": " ".join(row["candidate_ids"]),
            "decision": row["decision"],
            "status": row["status"],
            "language": row["language"],
            "locale": row["locale"],
            "categories": " ".join(row["categories"]),
            "sources": " ".join(row["sources"]),
            "agreement": row["agreement"],
            "dimensions": " ".join(row["dimensions"]),
            "blocker": row["blocker"],
            "critic": row["critic"],
            "search": " ".join(str(row[key]) for key in ("record_id", "input", "canonical", "decision", "candidate_ids")),
        }
        attr_text = " ".join(f'data-{key}="{_escape(value)}"' for key, value in attrs.items())
        review_evidence = (
            '<div class="evidence-grid">'
            + _annotation_panel("Reviewer A", row["review_a"])
            + _annotation_panel("Reviewer B", row["review_b"])
            + _comparison_panel(row["comparison"])
            + "</div>"
            + _adjudicator_panel(row["decisions"])
            + _critic_panel(row["decisions"])
        )
        cards.append(
            f'<article class="cluster" id="{_escape(anchor_id)}" {attr_text}>'
            '<header class="cluster-header">'
            f'<div><h3>Record: <span class="record-id">{_escape(row["record_id"])}</span></h3>'
            f'<p class="muted">Candidates: {_escape(row["candidate_ids"])} · A/B: {_escape(row["agreement"])}</p></div>'
            f'<span class="badge">{_escape(row["decision"])}</span></header>'
            f'<p><strong>Input:</strong> {_escape(row["input"])}</p>'
            f'<p><strong>Final:</strong> {_escape(row["canonical"])}</p>'
            f'<p class="muted">Status: {_escape(row["status"])} · Source: {_escape(row["sources"])} · Categories: {_escape(row["categories"])}</p>'
            f'<details><summary>Review evidence</summary>{review_evidence}</details>'
            '</article>'
        )
    css = """
:root{font-family:system-ui,sans-serif;color:#17202a;background:#f5f7fa}body{margin:0}main{max-width:1500px;margin:auto;padding:1rem}header,.panel,.cluster{background:#fff;border:1px solid #d8dee8;border-radius:.6rem;padding:1rem;margin-bottom:1rem}h1,h2,h3,h4,h5{margin-top:0}.muted{color:#657184}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:.6rem}.kpi{background:#eef4ff;border-radius:.4rem;padding:.7rem}.kpi strong,.kpi span{display:block}.kpi strong{font-size:1.25rem}.filters{display:flex;gap:.6rem;flex-wrap:wrap;align-items:end}.filters label{display:flex;flex-direction:column;font-size:.85rem}.filters input,.filters select{padding:.45rem;min-width:8rem}.filters input{min-width:15rem}.cluster-header{display:flex;justify-content:space-between;gap:1rem;align-items:start;border:0;padding:0}.cluster-header h3{margin-bottom:.2rem}.record-id{font-family:ui-monospace,monospace}.badge{background:#20334d;color:#fff;border-radius:99px;padding:.3rem .6rem}.evidence-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem}.reviewer{border:1px solid #d8dee8;border-radius:.4rem;padding:.7rem}.fields{margin:0}.field{display:grid;grid-template-columns:10rem 1fr;border-bottom:1px solid #edf0f4;padding:.3rem 0}.field dt{font-weight:600}.field dd{margin:0;white-space:pre-wrap;word-break:break-word}.table-scroll{overflow:auto}table{border-collapse:collapse;width:100%;margin-top:.5rem}th,td{border:1px solid #d8dee8;padding:.4rem;text-align:left;vertical-align:top}th{background:#edf1f6}.different td,.different th{background:#fff3cd}.comparison-state{font-weight:700}.decision{border-left:4px solid #5478a8;padding-left:.7rem;margin:.6rem 0}.critic{font-weight:700}.row-count{margin-left:auto;font-weight:600}button{padding:.4rem .7rem;border:1px solid #b9c4d2;border-radius:.4rem;cursor:pointer}@media(max-width:900px){.evidence-grid{grid-template-columns:1fr}.field{grid-template-columns:1fr}.filters input{min-width:10rem}}
"""
    script = """
const controls=[...document.querySelectorAll('[data-filter]')],rows=[...document.querySelectorAll('.cluster')],count=document.querySelector('#row-count');
function norm(x){return (x||'').toString().toLowerCase().trim()}
function filter(){let shown=0;rows.forEach(row=>{const keep=controls.every(c=>{const wanted=norm(c.value);if(!wanted)return true;return norm(row.dataset[c.dataset.filter]).split(' ').includes(wanted)||norm(row.dataset[c.dataset.filter]).includes(wanted)});row.hidden=!keep;if(keep)shown++});count.textContent=`${shown} / ${rows.length}`}
controls.forEach(c=>{c.addEventListener('input',filter);c.addEventListener('change',filter)});function route(){const id=decodeURIComponent(location.hash.replace(/^#(?:record=)?/,''));if(!id)return;const row=document.getElementById('record-'+id)||document.getElementById('cluster-'+id);if(row){row.hidden=false;row.scrollIntoView();row.classList.add('highlight');const d=row.querySelector('details');if(d)d.open=true}}filter();route();window.addEventListener('hashchange',route);
"""
    document = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Spokenform Gold review {_escape(batch_id or "batch")}</title><style>{css}</style></head><body><main><header><h1>Spokenform Gold review</h1><p class="muted">Batch {_escape(batch_id or "unspecified")} · Human review surface — open this report instead of inspecting JSONL.</p></header><section class="panel"><div class="kpis">{"".join(f'<div class="kpi"><strong>{_escape(value)}</strong><span>{_escape(label)}</span></div>' for label,value in kpis)}</div></section><section class="panel"><div class="filters"><label>Search<input type="search" data-filter="search" placeholder="record ID, candidate, input, output…"></label>{filter_html}<span class="row-count">Visible: <strong id="row-count"></strong></span></div><p class="muted">One card represents one sentence cluster. Expand a card for structured A/B, comparison, adjudicator, and critic evidence.</p></section><section id="clusters">{"".join(cards)}</section><script>{script}</script></main></body></html>'''
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


__all__ = ["render_review_html"]
