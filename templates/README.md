# Templates

Reusable prompt templates for the spokenform-gold production workflow. Copy
them into agent prompts, reviewer instructions, or batch handoff documents.

## Production workflow overview

The spokenform-gold benchmark is built through a structured review pipeline:

1. **Ingestion** — upstream benchmark sources (Async TN, PolyNorm, Proteno) are
   imported as quarantine candidates. Upstream expected outputs are preserved as
   evidence, never treated as ground truth.
2. **Coverage-driven selection** — candidates are ranked by which coverage gaps
   they fill (missing categories, missing languages, ambiguity, negative
   controls).
3. **Blind review** — two independent reviewers each annotate the same
   candidates without seeing upstream expected text, Spokenform output, or each
   other's work.
4. **Adjudication** — an adjudicator compares the two reviews, inspects
   disagreements, and produces a final decision.
5. **Promotion** — adjudicated records are promoted to the canonical corpus
   (`data/train`, `data/dev`, `data/test`) with frozen family-aware splits.
6. **Validation** — after every batch: validate, audit, check coverage, check
   conflicts, check controls, build a release.

The four templates below correspond to the four roles in this pipeline.

---

## Available templates

### coding-agent-first-task.md

**Use when:** giving a coding/annotation agent its first bounded task in this
repository.

Covers:
- establishing the real baseline (tests, validation, coverage, candidate release);
- verifying source-cache readiness;
- running the first full-source ingestion;
- upgrading the existing canonical records to strict review evidence;
- producing blind review inputs;
- hard rules and definition of done.

This is **not** a "build the whole dataset" prompt. It produces a reproducible
production baseline and a batch-0001 review package.

---

### reviewer-ab-task.md

**Use when:** sending a blind review artifact to an independent reviewer
(reviewer A or reviewer B).

Run this in **separate isolated contexts** for each reviewer. Neither reviewer
should see:
- `source.upstream_expected`;
- current Spokenform output;
- the other reviewer's annotation;
- adjudication results.

The template covers the 12 annotation steps each reviewer must complete
independently (span identification, category, semantics, ambiguity, policy,
canonical realization, accepted/rejected variants, sentence oracle, etc.).

---

### adjudicator-task.md

**Use when:** both blind reviews are complete and an adjudicator needs to
compare them and produce a final decision.

Inputs to provide:
- completed blind reviewer A artifact;
- completed blind reviewer B artifact;
- A/B comparison;
- source provenance;
- upstream expected text (revealed only now).

The template covers the 12 adjudication steps including disagreement
inspection, final semantic interpretation, disposition decision
(`promote_curated`, `promote_upstream`, `keep_external`, `reject`, `quarantine`,
`needs_review`), family assignment, and emitting a review-decision record.

---

### batch-handoff.md

**Use when:** a production batch is complete and you need to leave a structured
handoff report.

Fill in every section:
- source cache revisions and checks;
- ingestion row accounting;
- coverage before/after;
- review status (agreements, disagreements, adjudicated, needs_review);
- promotion dispositions;
- split assignments (frozen assignment changes must be NONE for existing
  families);
- release result;
- Spokenform benchmark result;
- unresolved blockers.

This report is the primary artifact for auditing what happened in a batch and
for handing off to the next agent or reviewer.

---

## How to use

1. **Read the relevant template** before starting the corresponding task.
2. **Copy the template content** into your agent prompt, reviewer instructions,
   or handoff document.
3. **Fill in the structured fields** (batch handoff) or **follow the
   instructions** (coding agent, reviewer, adjudicator).
4. **Do not weaken the hard rules** — they exist to protect benchmark
   integrity.

For the full production rules, data model, and source policy, see
[AGENTS.md](../AGENTS.md).
