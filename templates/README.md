# Active v2 templates

These templates describe the maintained sentence-centric v2 workflow:

- `coding-agent-first-task.md` - prepare observations and collect a logical batch
- `reviewer-ab-task.md` - independent bounded reviewer A/B work
- `adjudicator-task.md` - bounded semantic adjudication
- `integration-task.md` - mechanical integration into the canonical corpus
- `correction-task.md` - targeted correction by permanent record ID
- `release-publish-task.md` - immutable release verification and publication
- `batch-handoff.md` - compact batch continuation metadata

The canonical path is:

```text
prepare observations -> collect -> review-check -> adjudicate -> integrate -> validate -> report
```

Use generated HTML reports for human review. Do not ask humans to edit JSONL.
Deprecated runtime compatibility commands are not active authoring workflows.
