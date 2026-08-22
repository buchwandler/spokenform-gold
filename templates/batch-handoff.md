# Batch Handoff Template

> Extracted from `spokenform-gold-full-dataset-production-plan.md` §23.

Each batch should leave a Markdown or JSON handoff with:

---

**Batch ID:**
**Date:**

## Source cache
- async_tn revision:
- polynorm revision:
- proteno revision:
- revision checks passed:
- missing paths:

## Ingestion
- source rows:
- candidates:
- exclusions:
- row accounting:
- duplicate groups:
- conflicting-output groups:

## Coverage before
- records:
- categories observed:
- units:
- languages:
- gaps by kind:

## Review
- selected IDs:
- reviewer A complete:
- reviewer B complete:
- agreements:
- disagreements:
- adjudicated:
- needs_review:
- quarantined:

## Promotion
- promote_curated:
- promote_upstream:
- keep_external:
- reject:
- quarantine:
- promoted records:

## Splits
- new families:
- train:
- dev:
- test:
- frozen assignment changes: **MUST BE NONE for existing families**

## Coverage after
- records:
- categories observed:
- units:
- languages:
- gaps by kind:

## Release
- candidate release:
- stable release:
- manifest hash:

## Spokenform
- local Gold benchmark available:
- test split record count:
- canonical score:
- accepted score:
- failures needing implementation investigation:

## Unresolved blockers:
