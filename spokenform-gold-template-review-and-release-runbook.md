# Spokenform Gold v2 production runbook

The canonical authoring source is `data/corpus.jsonl`. New data follows:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

## Prepare and collect

Run `spokenform-gold doctor` first. Use configured source and work roots. Collect
at most 1,000 logical cases into a batch root. Do not search parent directories,
read the full corpus, or expose source caches to an agent context.

## Independent review

Give reviewers distinct fresh contexts and bounded packets. Packets are limited
by case count and serialized UTF-8 bytes. Reviewers must not receive source
observations, upstream expectations, current implementation output, or the other
review. Merge packet results atomically into complete A/B artifacts with one
truthful identity per slot.

## Gate and adjudicate

`review-check` is a full-batch deterministic gate. After it reports ready, the
adjudicator consumes bounded packets containing only selected case context,
reviews, relevant source observations, and policy evidence. Merge decisions
atomically. Finalization requires exactly one decision for every case ID and
valid accepted v2 records.

## Integrate and report

Run a dry integration first, then integrate with `--write`. Validate the full
canonical corpus and generate the HTML report. Preserve provenance and do not
adapt Gold to current Spokenform output. Use `batch-status` for continuation
metadata and exact lookup commands instead of broad filesystem searches.

## Human handoff

Provide compact counts, artifact hashes, validation state, coverage before/after,
blockers, and next action. Humans inspect HTML reports and do not edit JSONL.
