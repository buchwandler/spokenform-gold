# Spokenform Gold agent instructions

## Repository purpose

Spokenform Gold is the canonical benchmark, annotation, validation, coverage,
and oracle-governance layer for Spokenform. The benchmark policy defines Gold.
Do not change annotations to match current Spokenform output or an upstream
majority.

## Canonical v2 authoring contract

The canonical authoring source is the `data/corpus/` directory. Each language shard is `data/corpus/<language>.jsonl`. New sentence cases follow:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

A logical batch contains up to 1,000 cases. This is a file and completeness
contract, not an LLM prompt size. Review and adjudication use bounded packets
and deterministic checkpoints. Only complete artifacts enter the next gate.

## Non-negotiable data invariants

- Preserve source provenance and source expectations separately from Gold.
- Use stable `id`, `family_id`, language, locale, status, units, and oracle data.
- Use `gold`, `multi_valid`, `policy_choice`, `ambiguous`, `quarantine`, or
  `no_change` deliberately.
- Keep `canonical`, `accepted`, and `rejected` outputs distinct.
- `no_change` records equal their input, have no units, and have non-empty
  `negative_for` values.
- Represent ambiguity instead of inventing context.
- Keep source observations and licensing decisions explicit.
- Humans inspect generated HTML reports. Humans do not edit or enumerate JSONL.

## Role isolation

- Collection prepares observations, groups cases, and creates blind artifacts.
- Reviewer A and reviewer B work in distinct fresh contexts from bounded blind
  packets. They do not see source observations, upstream expectations, current
  Spokenform output, or the other review.
- `review-check` is a deterministic full-batch gate.
- Adjudication sees only selected adjudication packets after review-check is
  ready. It resolves semantics under policy and emits one decision per case.
- Integration is mechanical. It does not reinterpret semantics.
- Validation and reporting inspect complete files without printing their contents.
- Corrections are addressed by the permanent `record.id` and preserve identity.
- Release publication is separate from authoring and requires authorization.

## Context budget

Treat tool output as part of the model context budget.

1. Start from user-named artifacts and configured paths.
2. Run `spokenform-gold doctor` before filesystem hunting for work or cache paths.
3. Never recursively grep or search `.` for normal task discovery.
4. Never cat, recursively grep, or full-read `data/corpus/`. For language-scoped work, use only the required shard or an exact record lookup.
5. Never expose `context_spokenform_gold*`, Codecrate indexes or packs,
   external source caches, or the whole work root to the model.
6. Do not read all policy or documentation files up front.
7. Inspect metadata and counts first, then targeted records or excerpts.
8. Keep each inspection command at or below 20,000 output characters.
9. Prefer commands that write detailed JSON to disk and print compact summaries.
10. For JSONL, select by stable ID, case ID, or bounded packet. Never dump a
    complete file into context.
11. A 1,000-case batch is a logical batch, not one model invocation.
12. Review and adjudication packets must be bounded by case count and serialized
    UTF-8 bytes, and must resume deterministically.

## Task-scoped context routing

Do not preload repository documentation. Begin with the user-named file or
batch and `spokenform-gold doctor`. Read only the smallest authoritative source
needed for the decision:

- schema question: the relevant schema only;
- annotation semantics: `docs/ANNOTATION.md` and the relevant taxonomy/policy;
- provenance: `docs/SOURCE_POLICY.md`;
- review role: one relevant template;
- release: the release template and relevant release code/tests;
- implementation behavior: the focused module and focused tests.

Use `batch-status` for continuation metadata. Use exact record or case lookup
rather than broad search. Task-management state is not part of a focused data
operation unless the user explicitly requests that workflow or supplies a task
whose state is required.

## Active operational path

For new data, use `spokenform-gold batch-create --batch <BATCH_ID> --limit 1000`.
For one existing Gold defect, start with the permanent `record.id`; use `trace-record`, `prepare-correction`, and `apply-correction --write`.
Canonical review lineage is `data/lineage/review-evidence.jsonl`. Work-root snapshots, archive files, reports, and packets are never default evidence inputs.
Do not recursively inspect the work root or ask a human to locate JSONL rows or evidence files.

```bash
spokenform-gold doctor
spokenform-gold collect --observations <OBSERVATIONS> --reviewed data/corpus/ \
  --limit 1000 --batch <BATCH_ID> --out-root <WORK>/batches/<BATCH_ID>
spokenform-gold review-packet --batch <BATCH_ROOT> --slot A --max-cases 200 \
  --max-bytes 98304 --out <PACKET>
spokenform-gold review-check --batch <BATCH_ROOT> --review-a <A_COMPLETE> \
  --review-b <B_COMPLETE>
spokenform-gold adjudication-packet --batch <BATCH_ROOT> --review-a <A_COMPLETE> \
  --review-b <B_COMPLETE> --max-cases 100 --max-bytes 98304 --out <PACKET>
spokenform-gold integrate --batch <BATCH_ROOT>
spokenform-gold validate data/corpus/
spokenform-gold report --records data/corpus/ --out <REPORT.html>
```

Use `batch-status --batch <BATCH_ID>` to resolve configured paths and counts.
Use `agent-search` for bounded source search and `trace-case` or `trace-record`
for exact lookup. Detailed reports belong in files, not stdout.

## Validation and definition of done

Run the focused tests while implementing and the full suite before completion:

```bash
python -m pytest -q
ruff check .
ruff format --check .
make check
```

Do not weaken validation to accept broken source data. Before handoff, verify
schema validity, duplicate IDs, exact case coverage, family safety, source
provenance, semantic invariants, accepted/rejected disjointness, and negative
controls. Record unresolved blockers instead of hiding them.

## Human interface

Reports such as `review-report.html` are the human review surface.
The human supplies a stable record or batch identifier and receives compact
summaries plus generated HTML reports. Tools resolve artifact paths, hashes,
review evidence, and correction history. Do not ask humans for JSONL line
numbers, artifact enumeration, or manual edits.
