# Annotation protocol

Annotators answer independently:

1. What span requires normalization?
2. What category is it?
3. What does it mean in this context?
4. Is the written form genuinely ambiguous?
5. What is the preferred Spokenform realization?
6. Which alternative realizations preserve meaning?
7. Which plausible-looking realizations change meaning or violate policy?

Track disagreement separately for span/category, semantic interpretation,
canonical realization, and accepted variants.

High semantic disagreement should normally become `ambiguous`.

## Sentence-oracle review v2

Reviewers work independently on the sentence context and locale. The first pass must not expose `source.upstream_expected`, upstream expected strings, or another reviewer’s annotation. Use `spokenform-gold blind-review --reviewer-slot A|B` to create a review artifact that contains input, locale, source references, and an empty annotation.

Each reviewer records exact spans, categories, semantic objects, ambiguity, policy, unit canonical/accepted/rejected variants, the canonical full sentence, and every explicitly accepted full-sentence output. Compare disagreements by span, category, semantics, ambiguity, policy, unit realization, sentence canonical, sentence accepted set, and rejected variants. Only after both independent passes may an adjudicator inspect upstream expectations.

Use structured source error codes such as `source_wrong_semantics`, `source_policy_difference`, `source_ambiguous_context`, `source_span_error`, or `source_duplicate`; free-text notes do not replace these codes. Review states (`unreviewed`, `agreement`, `adjudication_required`, `adjudicated`, `release_ready`, and `legacy_review`) are distinct from semantic record statuses.

## Batch artifact and reviewer identity policy

Ingestion and ranking artifacts are proposals, not annotations. Each reviewer
slot receives a blind artifact that omits upstream expected text and current
Spokenform output. Reviewer A and reviewer B must complete independent semantic
judgments before comparison; an adjudicator then records the disagreement and
source-policy decision. Do not invent reviewer identities when only automated or
single-agent proposals exist.

Batch IDs are explicit and deterministic. External work roots may contain
`batch-0000`, `batch-0001`, and `batch-0002` artifacts, but those artifacts do not
alter canonical records or frozen split assignments.


## Sentence case workflow

Review one deduplicated sentence case, not one upstream row. The case contains all source observations for the same language, locale, and conservative normalized input. A and B receive only the sentence context and annotation policy. The adjudicator receives both completed reviews and source observations, then emits one final record or a deferred synthetic request.

Use the HTML batch report for human inspection. Do not ask reviewers or maintainers to edit JSONL or enumerate line numbers. A new synthetic sentence is a future candidate and cannot be promoted without fresh independent A/B review.
