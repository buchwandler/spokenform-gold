# Contributing benchmark records

1. Add new material to `data/candidates/`.
2. Run `spokenform-gold validate`.
3. Run `spokenform-gold conflicts --mode unit`.
4. Run `spokenform-gold coverage`.
5. Review semantic/category interpretation independently.
6. Adjudicate disagreements.
7. Promote only reviewed records into a gold split.

Never modify an upstream expected answer in-place. Preserve it as provenance and
record the Spokenform policy decision separately.
