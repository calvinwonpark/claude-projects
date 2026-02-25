.PHONY: install eval eval-online baseline test lint

install:
	pip install -e ".[dev]"

eval:
	evalkit run --suite cases/suites/rag_core.jsonl --mode offline

eval-online:
	evalkit run --suite cases/suites/rag_core.jsonl --mode online

baseline:
	python scripts/seed_baseline.py

test:
	pytest tests/ -v

lint:
	python -m py_compile evalkit/cli.py evalkit/config.py evalkit/types.py
