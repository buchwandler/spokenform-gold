# Templates

Reusable prompt templates for the Spokenform Gold production workflow. Copy them
into agent prompts, reviewer instructions, release-publication checklists, or
batch handoff documents. The benchmark policy in `AGENTS.md`, the schemas, the
taxonomy, and source policy remain authoritative.

## Production workflow overview

The workflow has separate tracks and role boundaries:

```text
real checkout and baseline
        |
        +--> legacy canonical re-review: blank A/B -> independent A/B
        |       -> canonical adjudicator -> isolated apply -> frozen split restore
        |
        +--> new data: quarantine ingestion -> coverage/ranking -> bounded batch
                -> independent A/B -> candidate adjudicator
                -> promotion/split/integration -> candidate release
                                                        |
                                                        v
                                      Spokenform integration -> stable gates
                                                        |
                                                        v
                                      explicit release publication -> verification
```

Upstream expected outputs are evidence, never Gold authority. A and B must run
in genuinely isolated contexts without seeing each other's work, current
Spokenform output, or hidden upstream expectations. Human review and
adjudication cannot be replaced by a proposal or an automated judge.

## Role templates

### `coding-agent-first-task.md` — T0 preparation/orchestration

**Use when:** starting from a fresh checkout.

The preparation agent establishes the real baseline, verifies the external
source cache, ingests and ranks quarantine candidates, creates blank review
artifacts, and prepares handoffs. It must stop before semantic review and must
not impersonate reviewers or adjudicators.

### `reviewer-ab-task.md` — T1/T2 independent review

**Use when:** completing reviewer A or reviewer B in a separate isolated
context.

The reviewer annotates spans, categories, semantics, ambiguity, policies,
canonical and accepted/rejected unit variants, and the explicit full-sentence
oracle. It must not inspect upstream expected output, current Spokenform output,
the other review, comparison, or decisions.

### `canonical-rereview-adjudicator-task.md` — T3a canonical re-review

**Use when:** existing canonical records with `legacy_review` or other
incomplete review evidence have two completed independent reviews.

Decisions are keyed by `sentence_oracle_id` and preserve existing record ID,
family ID, source identity, input, language, and locale. This role produces
adjudicated/release-ready oracle decisions for `apply-reviewed-oracles`; it is
not a candidate promotion or source-materialization decision.

### `adjudicator-task.md` — T3b candidate adjudication

**Use when:** a new candidate batch has two completed independent reviews.

This role compares reviews, resolves semantics, assigns a Spokenform-owned
family, decides source/license disposition, and emits one promotion decision per
candidate. It must not apply, split, copy, commit, or publish.

### `promote-split-commit-task.md` — T4 mechanical integration

**Use when:** candidate adjudication is complete.

The integration operator promotes only approved decisions into isolated staging,
runs the frozen family splitter, validates canonical-next, inspects oracle and
coverage diffs, copies only approved generated canonical shards, builds a
candidate release, and commits explicit paths. It never reinterprets semantics
or hand-picks splits.

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
