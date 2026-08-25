# Templates

Reusable prompt templates for the Spokenform Gold production workflow. Copy them
into agent prompts, reviewer instructions, release-publication checklists, or
batch handoff documents. The benchmark policy in `AGENTS.md`, the schemas, the
taxonomy, and source policy remain authoritative.

## Primary workflow: sentence-centric v2 data growth

New authoring work uses `data/corpus.jsonl` and the external work root. The primary path is:

```text
collect -> review-check -> adjudicate -> integrate -> validate -> report
```

`collect` groups all source observations by the conservative sentence identity `(language, locale, normalized input)` and emits one `case_id` plus one blind A row and one blind B row per case. The v2 reviewer contract uses `case_id`, `review_schema_version: "2.0.0"`, `language`, `locale`, `input`, `family_id`, `annotation: null`, and `review.status: "unreviewed"`. Reviewers write distinct `.complete.jsonl` artifacts without source expectations or current Spokenform output.

The adjudicator reads `cases.jsonl`, `context.jsonl`, both completed reviews, and policy/schema documentation. It writes exactly one `accept`, `exclude`, or `unresolved` row per `case_id` to `adjudicated.jsonl`; accepted rows contain a complete v2 `final_record`. Synthetic requests remain future candidates until independently reviewed.

Only after the review and adjudication gates pass may the integration context run a dry run and then `integrate --write`. It preserves source observations, rejects unresolved cases, and does not add `split` or legacy `sentence_oracle_id` state to `data/corpus.jsonl`. Generate `review-report.html` or `records.html` for human inspection rather than asking humans to edit JSONL.

Upstream expected outputs are evidence, never Gold authority. A and B must run in genuinely isolated fresh contexts without seeing each other's work, current Spokenform output, or hidden upstream expectations. Human review and adjudication cannot be replaced by a proposal or automated judge.

## Compatibility workflow

Legacy canonical re-review and split-based promotion templates remain available for compatibility. They are not the primary authoring path and must not be mixed with v2 `case_id` artifacts.

## Role templates

### `coding-agent-first-task.md` — T0 preparation/orchestration

**Use when:** starting from a fresh checkout.

The preparation agent establishes the real baseline, verifies the external
source cache, ingests and ranks quarantine candidates, creates blank review
artifacts, and prepares handoffs. It must stop before semantic review and must
not impersonate reviewers or adjudicators.

### `reviewer-ab-task.md` — v2 independent review

**Use when:** completing reviewer A or reviewer B for a `collect` batch in a separate fresh context.

The reviewer preserves `case_id`, language, locale, input, and family ID, fills the independent semantic annotation, and writes `a.complete.jsonl` or `b.complete.jsonl`. It must not inspect context/source observations, upstream expected output, current Spokenform output, the other review, comparison, or decisions.

### `canonical-rereview-adjudicator-task.md` — T3a canonical re-review

**Use when:** existing canonical records have two completed independent reviews. Run `spokenform-gold review-preflight` first; if it reports `ready=no`, stop without source inspection or adjudication.

Canonical records do not store `sentence_oracle_id`; the identity is derived from language, locale, and normalized input. Decisions preserve existing record ID, family ID, source identity, input, language, and locale. New artifacts use `canonical-a.blind.jsonl`, `canonical-a.complete.jsonl`, `canonical-b.blind.jsonl`, `canonical-b.complete.jsonl`, `preflight.json`, `comparison.jsonl`, `decisions.jsonl`, and `manifest.json`.

This role produces adjudicated/release-ready oracle decisions for `apply-reviewed-oracles`; it is not a candidate promotion or source-materialization decision.

### `adjudicator-task.md` — v2 candidate adjudication

**Use when:** a new `collect` batch has two completed independent reviews.

This role reads `cases.jsonl`, `context.jsonl`, `a.complete.jsonl`, and `b.complete.jsonl`, compares the independent annotations, resolves policy/source issues, and emits one `accept`, `exclude`, or `unresolved` row per `case_id` to `adjudicated.jsonl`. Accepted rows contain a complete v2 `final_record`. It must not apply, split, copy, commit, or publish.

### `promote-split-commit-task.md` — T4 mechanical integration

**Use when:** candidate adjudication is complete.

The integration operator promotes only approved decisions into isolated staging,
runs the frozen family splitter, validates canonical-next, inspects oracle and
coverage diffs, copies only approved generated canonical shards, builds a
candidate release, and commits explicit paths. It never reinterprets semantics
or hand-picks splits.

### `canonical-rereview-integration-task.md` — T3b mechanical canonical integration

**Use when:** canonical adjudication is complete and preflight/comparison checks pass. This role applies decisions in isolated output, verifies oracle/provenance/family/split invariants, runs strict checks, and obtains explicit approval before any Git copy. It never reinterprets semantics.

### `release-publish-task.md` — T5 publication

**Use when:** an approved commit has passed the local release gates and an
explicit publication decision is available.

The publication operator classifies candidate/experimental/stable tags using
the GitHub workflow, verifies the exact local release, obtains authorization,
checks public archives and checksums, and records downstream Spokenform pin
state. It does not mutate a published release.

### `batch-handoff.md` — T6 durable handoff

**Use when:** any batch, re-review milestone, integration, or release boundary
needs a structured machine-readable/human-readable report.

Fill every field, including hashes and separate local/public/pin states. Do not
claim completion from candidate work-root artifacts alone.

## Artifact isolation rules

| Artifact/operation                            | Allowed context                                    |
| --------------------------------------------- | -------------------------------------------------- |
| blank A/B review artifacts                    | T0 preparation                                     |
| `validate-review`                             | T1/T2 before reviewer handoff                      |
| semantic annotation                           | T1/T2 only, one reviewer per isolated context      |
| `compare-reviews`                             | T3a/T3b after both reviews complete                |
| canonical sentence-oracle decision            | T3a only                                           |
| candidate/source disposition decision         | T3b only                                           |
| `apply-reviewed-oracles`                      | following mechanical canonical integration context |
| promotion, split, copy, commit                | T4 only                                            |
| tag, GitHub publication, archive verification | T5 only, after explicit authorization              |
| downstream Spokenform pin                     | companion repository after public verification     |

## How to use

1. Read the relevant template and all policy files it names.
2. Replace every placeholder with truthful paths, IDs, versions, and identities.
3. Preserve the role boundary and stop conditions.
4. Keep work-root artifacts outside Git unless a separate policy explicitly
   requires a small audit artifact.
5. Record hashes for review, decision, promotion, split, and release artifacts
   in `batch-handoff.md`.
6. Run validation after every data change; never weaken coverage or maturity
   gates to obtain a green result.

For the full production rules, data model, and source policy, see
[AGENTS.md](../AGENTS.md).
