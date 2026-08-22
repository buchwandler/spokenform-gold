# Adjudicator Task Template

> Operational template for the Spokenform Gold production workflow. See `docs/DATA_GROWTH_BATCHES.md` and `docs/ANNOTATION.md`.

---

You are adjudicating two independent Spokenform Gold sentence-oracle reviews.

Inputs:

- completed blind reviewer A artifact;
- completed blind reviewer B artifact;
- A/B comparison;
- source provenance;
- upstream expected text may be revealed only now.

For every sentence:

1. verify that A and B reviewed the same input/language/locale independently;
2. inspect disagreements by span, category, semantic meaning, ambiguity,
   policy, unit realization, accepted variants, sentence canonical, and
   rejected variants;
3. decide the final semantic interpretation;
4. decide canonical and explicitly accepted outputs;
5. preserve meaningful alternatives;
6. record rejected variants and reasons;
7. record source error codes when the upstream source is wrong/different;
8. choose promote_curated, promote_upstream, keep_external, reject,
   quarantine, or needs_review;
9. assign/confirm a stable family_id;
10. record license_disposition;
11. preserve upstream references as lineage when appropriate;
12. emit a review-decision record accepted by
    schemas/review-decision.schema.json.

Do not choose an answer because it matches current Spokenform.
Do not majority-vote sources.
Do not relabel copied restricted text as spokenform_curated.
If the disagreement cannot be resolved from context, keep it ambiguous,
quarantined, or needs_review.
