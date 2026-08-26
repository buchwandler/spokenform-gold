# Spokenform Gold

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

Validate the canonical corpus and create reports without dumping its contents:

```bash
spokenform-gold validate data/corpus/
spokenform-gold coverage data/corpus/ \
  --targets taxonomy/coverage_targets.json \
  --json <WORK>/reports/coverage.json
spokenform-gold conflicts data/corpus/ --mode unit \
  --json <WORK>/reports/conflicts.json
spokenform-gold report --records data/corpus/ \
  --out <WORK>/reports/corpus.html
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
