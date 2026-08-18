.PHONY: check test stats validate coverage conflicts split score adjudicate release-check

check: test stats validate coverage conflicts score release-check

test:
	python -m unittest discover -s tests -v

stats:
	PYTHONPATH=. python -m spokenform_gold.cli stats data/dev/*.jsonl data/test/*.jsonl

validate:
	PYTHONPATH=. python -m spokenform_gold.cli validate data/dev/*.jsonl
	PYTHONPATH=. python -m spokenform_gold.cli validate data/test/*.jsonl
	PYTHONPATH=. python -m spokenform_gold.cli validate data/judge_gold/*.jsonl --judge

coverage:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli coverage data/dev/*.jsonl data/test/*.jsonl --targets taxonomy/coverage_targets.json --json reports/coverage.json

conflicts:
	PYTHONPATH=. python -m spokenform_gold.cli conflicts data/dev/*.jsonl data/test/*.jsonl --mode unit --fail-on-conflict --out reports/conflicts.json

split:
	rm -rf /tmp/spokenform-gold-split-check
	PYTHONPATH=. python -m spokenform_gold.cli split data/dev/*.jsonl data/test/*.jsonl --seed 20260818 --out-root /tmp/spokenform-gold-split-check

score:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli score data/test/*.jsonl --predictions tests/fixtures/predictions/sample_predictions.jsonl --mode canonical --json reports/score.json

adjudicate:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli adjudicate-queue data/candidates/*.jsonl --conflicts reports/conflicts.json --coverage reports/coverage.json --out reports/adjudication.jsonl

release-check:
	rm -rf dist/spokenform-gold-v0.1.0
	PYTHONPATH=. python -m spokenform_gold.cli release-check --version 0.1.0 --data data/dev data/test --out dist/spokenform-gold-v0.1.0
