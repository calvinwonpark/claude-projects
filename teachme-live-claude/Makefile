.PHONY: dev eval eval-realtime-smoke lint

dev:
	uvicorn app:app --host 0.0.0.0 --port 8000 --reload

eval:
	python evals/run_eval.py --mode $${EVAL_MODE:-offline}

eval-realtime-smoke:
	python evals/run_eval.py --mode offline --suite realtime_smoke

lint:
	python -m py_compile app.py session_state.py stt_stream.py tts_stream.py websocket_protocol.py
