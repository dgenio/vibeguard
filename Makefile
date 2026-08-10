.PHONY: help install-dev test lint format-check typecheck ci clean demo docs docs-check check-versions bench bench-small bench-medium bench-large bench-scenarios bench-precision bench-precision-check update-goldens

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

install-dev: ## Install package in editable mode with local dev tooling
	python -m pip install --upgrade pip
	python -m pip install -e . --group dev

test: ## Run tests with coverage
	pytest tests/ -v --cov=vibeguard --cov-report=term-missing --cov-report=xml

lint: ## Run ruff linter
	ruff check vibeguard/ tests/ benchmarks/

format-check: ## Check code formatting with ruff
	ruff format --check vibeguard/ tests/ benchmarks/

typecheck: ## Run mypy type checking
	mypy vibeguard/

docs: ## Regenerate docs/rules.md from the rule registry
	python scripts/generate_rule_docs.py

docs-check: ## Fail if docs/rules.md is out of date
	python scripts/generate_rule_docs.py --check

check-versions: ## Fail if README/docs/action version references have drifted
	python scripts/check_doc_versions.py

ci: lint format-check typecheck docs-check bench-precision-check check-versions test ## Run full CI pipeline locally

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info .pytest_cache .mypy_cache .coverage htmlcov/ .ruff_cache/ coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

demo: ## Run vibeguard against bundled examples
	vibeguard scan --path examples/vulnerable-node-package
	vibeguard scan --path examples/vulnerable-python-package

bench: bench-small ## Run the default (small) benchmark

bench-small: ## Generate and scan a small synthetic repo (~500 KB)
	python -m benchmarks.run --size small

bench-medium: ## Generate and scan a medium synthetic repo (~5 MB)
	python -m benchmarks.run --size medium

bench-large: ## Generate and scan a large synthetic repo (~20 MB)
	python -m benchmarks.run --size large

bench-scenarios: ## Evaluate detection + false-positive baseline on scenario fixtures
	python -m benchmarks.scenarios

bench-precision: ## Measure precision/recall/F1 on the labeled corpus + refresh docs/precision-report.md
	python -m benchmarks.precision
	python -m benchmarks.precision --markdown

bench-precision-check: ## Fail if docs/precision-report.md is out of date
	python -m benchmarks.precision --check

update-goldens: ## Regenerate golden reporter snapshots in tests/fixtures/golden/
	PYTEST_UPDATE_GOLDENS=1 pytest tests/test_reporters_golden.py -q
