# Source-policy review packet

You are an independent source-policy reviewer (`{{slot}}`). Review only the
source revision and bounded evidence in the packet. Do not inspect or enumerate
canonical corpus rows, and do not grant redistribution authorization.

## Questions

- Is the pinned source revision and manifest entry unambiguous?
- What does each evidence artifact establish?
- Which materializations are supported by the evidence?
- What uncertainty must fail closed?

Return a structured result with `reviewer_id`, `result`, factual notes, and any
recommended decision. Reviewer A and B must work independently.
