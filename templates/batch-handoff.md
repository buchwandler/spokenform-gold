# Batch Handoff Template

> Use for every production batch, canonical re-review milestone, integration
> commit, or release boundary. Fill every field; use `NONE`, `NOT_RUN`, or
> `NOT_PUBLISHED` explicitly rather than leaving an ambiguous blank.

---

**Batch/review ID:**
**Date:**
**Operator/context:**
**Repository commit at start:**
**Repository commit at handoff:**
**Repository status clean at handoff:** yes/no

## Source cache and provenance

- async_tn pinned revision:
- polynorm pinned revision:
- proteno pinned revision:
- `sources/manifest.json` SHA256:
- `sources/source-lock.json` SHA256:
- source checkout revisions verified: yes/no
- required source paths verified: yes/no
- missing paths or revision blockers:
- source materialization policy reviewed: yes/no
- source/license decision blockers:

## Ingestion and row accounting

- source rows discovered:
- imported candidate rows:
- candidate rows selected:
- exclusions:
- duplicate groups:
- conflicting-output groups:
- `row_accounting_ok`:
- every source row accounted for: yes/no
- candidate records validated: yes/no
- upstream identities and expected outputs preserved: yes/no
- candidate/quarantine rows auto-promoted: **MUST BE NONE**
- ingestion summary path and SHA256:
- upstream pool summary path and SHA256:
- dedupe report path and SHA256:
- conflicts report path and SHA256:
- exclusions report path and SHA256:

## Coverage before

- records:
- categories observed:
- units:
- languages:
- locales:
- status distribution:
- source distribution:
- coverage report path and SHA256:
- total coverage gaps:
- gaps by kind:
- stable-required gaps:
- stable coverage gap count:
- negative-control gaps:
- ambiguity-family gaps:

## Review artifacts and independence

- candidate batch path and SHA256:
- selected candidate IDs:
- selected sentence-oracle IDs:
- canonical review A blank path:
- canonical review A blank SHA256:
- canonical review B blank path:
- canonical review B blank SHA256:
- candidate review A blank path:
- candidate review A blank SHA256:
- candidate review B blank path:
- candidate review B blank SHA256:
- reviewer A identity:
- reviewer B identity:
- reviewer identities distinct and truthful: yes/no
- reviewer A completed path and SHA256:
- reviewer B completed path and SHA256:
- comparison path and SHA256:
- A/B row and identity sets match: yes/no
- A/B agreements:
- A/B disagreements:
- canonical adjudication path and SHA256:
- candidate decisions path and SHA256:
- adjudicator identity:
- adjudicated canonical records:
- release-ready canonical records:
- candidate decisions complete: yes/no
- needs_review:
- ambiguous:
- quarantined:
- source error-code counts:

## Promotion and canonical integration

- promotion staging path and SHA256:
- promotion report path and SHA256:
- candidate count:
- promote_curated:
- promote_upstream:
- keep_external:
- reject:
- quarantine:
- needs_review:
- promoted records:
- promotion accounting reconciles exactly: yes/no
- canonical re-review apply output root:
- canonical re-review report SHA256:
- oracle diff path and SHA256:
- existing record/source/family identities preserved: yes/no

## Frozen split registry

- split registry before path and SHA256:
- split registry after path and SHA256:
- new family IDs:
- train records/families:
- dev records/families:
- test records/families:
- existing family assignment changes: **MUST BE NONE**
- registry changes additions only: yes/no
- canonical-next path:
- canonical-next validation result:

## Coverage after

- records:
- categories observed:
- units:
- languages:
- locales:
- status distribution:
- source distribution:
- coverage report path and SHA256:
- total coverage gaps:
- stable-required gaps:
- negative-control gaps:
- ambiguity-family gaps:
- coverage moved in the expected direction: yes/no

## Validation and release gates

- canonical validation command/result:
- non-strict Gold audit command/result:
- strict Gold audit command/result:
- strict audit blocker count:
- unit conflict command/result:
- unit conflict count:
- control validation command/result:
- control coverage command/result:
- control coverage gap count:
- judge-gold validation command/result:
- `make check` result:
- release-check version:
- release-check maturity: experimental/candidate/stable
- release-check profile:
- local release path:
- release manifest SHA256:
- release notes path:
- records.html path:
- release result: pass/fail/not_run
- stable gate blockers remaining:

## Release and publication state

Keep these states separate:

- local release built: yes/no
- local release manifest SHA256:
- public release authorized: yes/no
- publication authorization note/path:
- public release published: yes/no
- GitHub tag:
- GitHub release/tag URL, or **NOT_PUBLISHED**:
- published maturity/prerelease flag:
- `.tar.gz` asset:
- `.zip` asset:
- archive checksum asset:
- archive checksum verification: pass/fail/not_run
- unpacked manifest verification: pass/fail/not_run
- published release immutable and unchanged after verification: yes/no

## Spokenform integration and pin

- local Gold benchmark available: yes/no
- Gold version:
- Gold manifest SHA256:
- Spokenform version/commit:
- evaluation profile:
- test split record count:
- canonical score:
- accepted score:
- no-change score:
- false-positive normalization rate:
- failure IDs:
- implementation investigation blockers:
- companion Spokenform benchmark run: yes/no
- companion Spokenform pin updated: yes/no
- companion pin commit/PR:

## Files and commits

- exact files changed:
- exact files staged:
- baseline commit:
- ending commit:
- batch commit:
- unrelated changes present: yes/no
- `git diff --check`: pass/fail
- handoff artifact path and SHA256:

## Unresolved blockers and next action

- source/revision blockers:
- review-independence blockers:
- semantic/adjudication blockers:
- license/materialization blockers:
- split/identity blockers:
- strict-audit blockers:
- stable coverage/control blockers:
- publication blockers:
- next action and intended role:
