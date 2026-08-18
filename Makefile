.PHONY: check test validate coverage

check: test validate coverage

test:
	python -m unittest discover -s tests -v

validate:
	PYTHONPATH=src python -m spokenform_gold.cli validate data/dev/sample.jsonl
	PYTHONPATH=src python -m spokenform_gold.cli validate data/judge_gold/sample.jsonl --judge

coverage:
	mkdir -p reports
	PYTHONPATH=src python -m spokenform_gold.cli coverage data/dev/sample.jsonl --targets taxonomy/coverage_targets.json --json reports/coverage.json
