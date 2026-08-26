.PHONY: check lint test stats candidate-stats validate validate-corpus validate-controls coverage control-coverage conflicts split score adjudicate judge-calibrate release-check

check: lint test stats candidate-stats validate validate-corpus validate-controls coverage control-coverage conflicts adjudicate score judge-calibrate release-check

lint:
	ruff check .

test:
	pytest -q

stats:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli stats data/train/*.jsonl data/dev/*.jsonl data/test/*.jsonl --json reports/release_stats.json

candidate-stats:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli stats data/candidates/*.jsonl --json reports/candidate_stats.json

validate:
	PYTHONPATH=. python -m spokenform_gold.cli validate data/train/*.jsonl
	PYTHONPATH=. python -m spokenform_gold.cli validate data/dev/*.jsonl
	PYTHONPATH=. python -m spokenform_gold.cli validate data/test/*.jsonl
	PYTHONPATH=. python -m spokenform_gold.cli validate data/judge_gold/*.jsonl --judge

validate-controls:
	PYTHONPATH=. python -m spokenform_gold.cli validate-controls data/controls/*.jsonl

coverage:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli coverage data/train/*.jsonl data/dev/*.jsonl data/test/*.jsonl --targets taxonomy/coverage_targets.json --json reports/coverage.json

control-coverage:
	PYTHONPATH=. python -m spokenform_gold.cli control-coverage data/controls/*.jsonl --targets taxonomy/coverage_targets.json --json reports/control_coverage.json

conflicts:
	PYTHONPATH=. python -m spokenform_gold.cli conflicts data/train/*.jsonl data/dev/*.jsonl data/test/*.jsonl --mode unit --fail-on-conflict --out reports/conflicts.json

split:
	rm -rf /tmp/spokenform-gold-split-check
	PYTHONPATH=. python -m spokenform_gold.cli split data/train/*.jsonl data/dev/*.jsonl data/test/*.jsonl --seed 20260818 --registry splits/family_assignments.json --out-root /tmp/spokenform-gold-split-check

score:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli score data/test/*.jsonl --predictions tests/fixtures/predictions/sample_predictions.jsonl --mode canonical --json reports/score.json

adjudicate:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli adjudicate-queue data/candidates/*.jsonl --conflicts reports/conflicts.json --coverage reports/coverage.json --out reports/adjudication.jsonl

judge-calibrate:
	mkdir -p reports
	PYTHONPATH=. python -m spokenform_gold.cli judge-calibrate data/judge_gold/*.jsonl --predictions tests/fixtures/predictions/judge_predictions.jsonl --json reports/judge_calibration.json

release-check:
	rm -rf dist/spokenform-gold-v0.1.0-exp
	PYTHONPATH=. python -m spokenform_gold.cli release-check --version 0.1.0-exp --data data/train data/dev data/test --controls data/controls --registry splits/family_assignments.json --maturity experimental --out dist/spokenform-gold-v0.1.0-exp

validate-corpus:
	PYTHONPATH=. python -m spokenform_gold.cli validate data/corpus/
