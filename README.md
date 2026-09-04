# Spokenform Gold

For new data, run `spokenform-gold batch-create --batch <BATCH_ID> --limit 1000`. For an existing defect, start with the permanent `record.id` and use `trace-record`, `prepare-correction`, then `apply-correction --write`. The canonical lineage is `data/lineage/review-evidence.jsonl`; arbitrary work-root snapshots are not evidence inputs.

The canonical corpus currently contains 19,789 reviewed Gold records. This count is distinct from any public release count: local benchmarking uses the complete corpus, while public records are selected by explicit source/revision/materialization policy.

Spokenform Gold is the benchmark, annotation, validation, coverage, and oracle
governance layer for Spokenform. Gold is defined by benchmark policy and reviewed
semantic evidence, not by current implementation output or source majority vote.

## Canonical authoring workflow

The canonical authoring source is the `data/corpus/` directory, with one `data/corpus/<language>.jsonl` shard per language. New sentence cases follow:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

A logical batch contains up to 1,000 cases. Reviewers and adjudicators process
bounded packets selected by stable case ID and serialized UTF-8 byte limits. The
complete files remain deterministic source artifacts and full-batch gates are
not weakened by packetization.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
spokenform-gold doctor
spokenform-gold collect \
  --observations <OBSERVATIONS> \
  --reviewed data/corpus/ \
  --limit 1000 --batch batch-0001 \
  --out-root <WORK>/batches/batch-0001
```

Use `batch-status --batch <BATCH_ID>` for compact continuation metadata. Use
`review-packet` and `adjudication-packet` for bounded semantic work. Use
`agent-search` for bounded source search. Use `trace-record` and `trace-case` for
exact lookup. Normal commands print summaries; detailed reports are written to
files.

## Data model

Canonical records preserve stable identity, language, locale, family, status,
units, oracle data, source observations, provenance, and licensing decisions.
Statuses include `gold`, `multi_valid`, `policy_choice`, `ambiguous`,
`quarantine`, and `no_change`. Keep canonical, accepted, and rejected outputs
separate. Negative controls are first-class records and must remain unchanged.

Read only the focused policy or schema needed for a decision:

- `DATA_MODEL.md` for record structure;
- `docs/ANNOTATION.md` for semantic annotation;
- `docs/SOURCE_POLICY.md` for provenance and redistribution;
- `taxonomy/categories.json` and `taxonomy/policies.json` for registered policy;
- `templates/` for the active role contract.

## Commands

Validate the canonical corpus and inspect the full-corpus/public-release distinction without dumping its contents:

```bash
spokenform-gold validate data/corpus/
spokenform-gold corpus-status --records data/corpus/
spokenform-gold release-preflight --data data/corpus/ --out <WORK>/reports/release-preflight.json
spokenform-gold benchmark --corpus data/corpus/ \
  --prepare-module <MODULE:FUNCTION> --mode accepted \
  --results-dir <WORK>/benchmarks/full-corpus
```

`corpus-status` reports canonical, review-complete, retry, embedded, external-reference, blocked, and local benchmark counts. `release-preflight` writes a complete stable-ID partition and explicit source-policy blockers. A local benchmark writes `artifact_kind=local_canonical_benchmark` and `publishable=false`; it does not require a public release manifest.

For public builds, provide approved source decisions. Do not use a curated-only allowlist as a substitute for source policy:

```bash
spokenform-gold release \
  --version 0.1.0-exp.2 --data data/corpus/ --controls data/controls \
  --maturity experimental --coverage-profile all-active \
  --conflict-adjudication release/conflict-adjudication.json \
  --source-decisions release/source-release-decisions.json \
  --out <WORK>/releases/v0.1.0-exp.2
```
Integration is mechanical and requires complete reviewed decisions:

```bash
spokenform-gold integrate --batch <BATCH_ROOT> --corpus data/corpus/
spokenform-gold integrate --batch <BATCH_ROOT> --corpus data/corpus/ --write
```

If a consumer requires family-safe exports, generate them from the immutable
canonical corpus. Export layouts are consumer artifacts, not editable authoring
state.

Reports such as `review-report.html` are the human review surface.

## Human review

Humans receive compact summaries and generated HTML reports. Tools resolve
artifact paths, hashes, review lineage, and correction history from stable
batch or record IDs. Do not ask humans to edit or enumerate JSONL.

## Development

```bash
python -m pytest -q
ruff check .
ruff format --check .
make check
```

Deprecated runtime compatibility commands may remain available for consumers,
but they are not the maintained authoring workflow described here.
