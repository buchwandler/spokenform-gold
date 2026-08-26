# Coding Agent: Sentence-Centric v2 Batch Preparation

Use this role to prepare one reproducible logical batch. It does not perform
semantic review, adjudication, integration, or release publication.

## Contract

The canonical source is `data/corpus.jsonl`:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

A batch may contain up to 1,000 cases. Do not place the whole batch in one model
context. Reviewers and adjudicators consume bounded packets and preserve their
complete artifacts on disk.

## Context budget

Start with the user-named batch and `spokenform-gold doctor`. Do not recursively
search the repository, read the full corpus, expose work/cache directories, or
preload all policy files. Keep inspection output below 20,000 characters. Use
metadata, exact IDs, and packet files. Never use current Spokenform output as
Gold evidence.

## Role boundary

You may verify configured paths, prepare source observations, collect the next
logical batch, and prepare blind reviewer artifacts. You must not fill either
review, inspect another reviewer’s answers, adjudicate, write accepted records,
change policy, or manufacture reviewer identities or evidence.

## Collection

```bash
spokenform-gold doctor
spokenform-gold collect \
  --observations <OBSERVATIONS> \
  --reviewed data/corpus.jsonl \
  --limit 1000 \
  --batch <BATCH_ID> \
  --out-root <WORK>/batches/<BATCH_ID>
```

The batch root contains the deterministic case, context, blind-review, and
batch metadata artifacts. Preserve source lineage and quarantine imported
observations. Do not copy hidden source expectations into blind artifacts.

## Handoff

Give reviewer A and reviewer B distinct fresh contexts and truthful stable
identities. Each reviewer receives only bounded packets projected from its blind
artifact. A logical batch may require many packet invocations. The final
`a.complete.jsonl` and `b.complete.jsonl` files must each cover the exact full
case-ID set once. Partial checkpoints are not handoff artifacts.

The human receives compact status and generated HTML reports, not JSONL rows to
edit. Stop on missing paths, failed accounting, incomplete artifacts, or invalid
review independence, and report the named blocker.
