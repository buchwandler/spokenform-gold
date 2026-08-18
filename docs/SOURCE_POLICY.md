# Source policy

PolyNorm, async-TN and Proteno remain external benchmark sources.

MVP rules:

- never silently rewrite an upstream record;
- import source examples into `data/candidates/`, not directly into gold;
- record benchmark name and source identifier;
- preserve upstream expected text in provenance where available;
- do not redistribute full upstream corpora until license compatibility and
  attribution requirements are reviewed;
- quarantine suspicious language/transcription/annotation rows instead of
  treating an automated judge as authoritative.
