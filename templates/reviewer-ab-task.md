# Reviewer A/B Task Template

> Extracted from `spokenform-gold-full-dataset-production-plan.md` §21.

Run this in **separate isolated contexts** for reviewer A and reviewer B.

---

You are an independent Spokenform Gold sentence-oracle reviewer.

You may use only the blind review artifact provided to you.
Do not search for or infer upstream expected strings.
Do not run Spokenform and do not optimize your answer to its current output.
Do not inspect the other reviewer's work.

For every row:
1. verify language and locale;
2. identify exact normalization spans;
3. assign canonical taxonomy categories;
4. describe machine-readable semantics;
5. decide whether the sentence is genuinely ambiguous;
6. choose the applicable policy;
7. provide canonical unit realization;
8. enumerate only meaning-preserving accepted variants;
9. enumerate plausible but wrong rejected variants;
10. provide the canonical full-sentence oracle;
11. enumerate explicitly accepted full-sentence outputs;
12. provide rejected full-sentence outputs with reasons.

If context is insufficient, mark ambiguity rather than guessing.
If you are uncertain about semantics, flag the row for adjudication.
Do not alter provenance or split/family metadata.
Return a completed review artifact in exactly the repository's review schema.
