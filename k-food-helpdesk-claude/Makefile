up:
	docker compose up -d --build

index:
	docker compose run --rm indexer

logs:
	docker compose logs -f

down:
	docker compose down

rebuild:
	docker compose down && docker compose build --no-cache && docker compose up -d

eval:
	docker compose run --build --rm -v "$$(pwd)/evals:/app/evals" server python evals/run_eval.py

eval-local:
	python evals/run_eval.py
