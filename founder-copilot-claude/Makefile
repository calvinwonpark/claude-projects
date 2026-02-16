up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

index:
	docker compose run --rm indexer

eval:
	docker compose run --build --rm -e EVAL_MODE=full -v "$$(pwd)/evals:/app/evals" foundercopilot python evals/run_eval.py

eval-retrieval:
	docker compose run --build --rm -e EVAL_MODE=retrieval_only -v "$$(pwd)/evals:/app/evals" foundercopilot python evals/run_eval.py
