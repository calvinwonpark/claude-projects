import json
import logging
import os
import re
import time
from collections import deque
from dataclasses import asdict
from typing import Any

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.audit import AuditRecord, build_prompt_hash, get_recent_audit_logs, insert_audit_log
from server.prompts.system import SYSTEM_PROMPT
from server.providers.claude_client import ClaudeClient
from server.providers.embeddings import build_embeddings_provider
from server.rag.reranker import rerank_docs
from server.rag.context_builder import build_retrieval_context
from server.rag.retriever import RetrievedDoc, Retriever
from server.reliability.citations import enforce_citation_policy
from server.security import AuthContext, authorize_audit_access, maybe_redact, require_auth
from server.session_store import SessionTurn, build_session_store

load_dotenv()
logger = logging.getLogger(__name__)

app = FastAPI(title="K-Food Helpdesk Claude API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3002", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class Metrics:
    def __init__(self) -> None:
        self.total_requests = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.latencies = deque(maxlen=1000)

    def observe(self, latency: float, input_tokens: int | None, output_tokens: int | None) -> None:
        self.total_requests += 1
        self.latencies.append(latency)
        if input_tokens is not None:
            self.total_input_tokens += input_tokens
        if output_tokens is not None:
            self.total_output_tokens += output_tokens

    def p95(self) -> float:
        if not self.latencies:
            return 0.0
        arr = sorted(self.latencies)
        idx = min(int(len(arr) * 0.95), len(arr) - 1)
        return float(arr[idx])


metrics = Metrics()
embeddings = build_embeddings_provider()
retriever = Retriever(embeddings=embeddings)
session_store = build_session_store()
claude = ClaudeClient(
    api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    primary_model=os.getenv("CLAUDE_PRIMARY_MODEL", "claude-3-5-sonnet-latest"),
    fallback_model=os.getenv("CLAUDE_FALLBACK_MODEL", "claude-3-haiku-latest"),
    extra_models=[
        m.strip()
        for m in os.getenv(
            "CLAUDE_MODEL_CANDIDATES",
            "claude-3-haiku-20240307,claude-3-sonnet-20240229,claude-3-5-haiku-20241022",
        ).split(",")
        if m.strip()
    ],
    temperature=float(os.getenv("CLAUDE_TEMPERATURE", "0.2")),
    max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS", "900")),
    request_timeout_ms=int(os.getenv("REQUEST_TIMEOUT_MS", "15000")),
)


class ChatReq(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    doc_type: str | None = None


class SearchReq(BaseModel):
    message: str = Field(min_length=1)
    session_id: str | None = None
    doc_type: str | None = None
    k: int = 8


def _detect_language(text: str) -> str:
    return "ko" if re.search(r"[가-힣]", text or "") else "en"


def _to_message_history(turns: list[SessionTurn]) -> list[dict[str, Any]]:
    return [{"role": t.role, "content": t.text} for t in turns[-20:] if t.role in {"user", "assistant"}]


def _build_retrieval_docs(message: str, doc_type: str | None, k: int) -> list[RetrievedDoc]:
    filters = {"doc_type": doc_type} if doc_type else None
    retrieved = retriever.retrieve_top_k_from_text(message, k=k, filters=filters)
    return rerank_docs(message, retrieved, mode=os.getenv("RERANK_MODE", "heuristic"))


def _sources_for_citations(citations: list[str], docs: list[RetrievedDoc]) -> list[str]:
    if not docs:
        return []
    id_to_source = {str(doc.doc_id): doc.source for doc in docs}
    ordered_sources: list[str] = []
    for citation in citations:
        if not citation.startswith("doc:"):
            continue
        doc_id = citation.split(":", 1)[1]
        source = id_to_source.get(doc_id)
        if source and source not in ordered_sources:
            ordered_sources.append(source)
    if ordered_sources:
        return ordered_sources
    # Fallback: if citations are missing or invalid, return source list from retrieved docs.
    dedup_sources: list[str] = []
    for doc in docs:
        if doc.source not in dedup_sources:
            dedup_sources.append(doc.source)
    return dedup_sources


def _sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": "K-Food Helpdesk API (Claude + RAG)",
        "endpoints": {
            "GET /": "API information",
            "GET /health": "Health check",
            "GET /metrics": "Request, token, and p95 latency metrics",
            "GET /models": "Cached Anthropic model availability and selected models",
            "POST /search": "Debug retrieval with scores",
            "POST /chat": "Structured RAG chat completion",
            "POST /chat/stream": "SSE token streaming chat",
            "GET /audit/recent": "Recent audit logs (jwt or admin api key)",
        },
    }


@app.on_event("startup")
def startup_warmup() -> None:
    status = claude.warmup_model_selection()
    logger.info("Claude model warmup complete: selected=%s", status.get("active_fallback_chain"))


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/metrics")
def get_metrics(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    _ = auth
    p95 = metrics.p95()
    total_tokens = metrics.total_input_tokens + metrics.total_output_tokens
    return {
        "total_requests": metrics.total_requests,
        "total_input_tokens": metrics.total_input_tokens,
        "total_output_tokens": metrics.total_output_tokens,
        "total_tokens": total_tokens,
        "tokens_per_request": (total_tokens / metrics.total_requests) if metrics.total_requests else 0,
        "p95_latency_seconds": round(p95, 4),
        "p95_latency_ms": round(p95 * 1000, 2),
        "cache": retriever.cache_stats(),
    }


@app.post("/search")
def search(req: SearchReq, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    _ = auth
    docs = _build_retrieval_docs(req.message, req.doc_type, req.k)
    payload = [
        {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source": doc.source,
            "chunk_index": doc.chunk_index,
            "score": round(doc.score, 6),
            "doc_type": doc.doc_type,
            "content_snippet": doc.content_snippet,
        }
        for doc in docs
    ]
    return {"results": payload}


@app.get("/models")
def models(auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    _ = auth
    return claude.get_model_status()


def _build_claude_messages(session_id: str, user_message: str, context_json: str) -> list[dict[str, str]]:
    state = session_store.get(session_id)
    target_lang = _detect_language(user_message)
    lang_instruction = (
        "Language instruction: Reply in Korean for this turn."
        if target_lang == "ko"
        else "Language instruction: Reply in English for this turn."
    )
    messages: list[dict[str, str]] = []
    messages.extend(_to_message_history(state.turns))
    messages.append(
        {
            "role": "user",
            "content": "Retrieved context JSON (use this as the only factual grounding):\n" + context_json,
        }
    )
    messages.append({"role": "user", "content": lang_instruction})
    messages.append({"role": "user", "content": user_message})
    return messages


def _update_session(session_id: str, user_message: str, assistant_answer: str, citations: list[str]) -> None:
    state = session_store.get(session_id)
    state.target_language = _detect_language(user_message)
    state.turns.extend(
        [
            SessionTurn(role="user", text=user_message),
            SessionTurn(role="assistant", text=assistant_answer),
        ]
    )
    state.retrieval_cache[user_message] = [int(c.split(":")[1]) for c in citations]
    session_store.upsert(session_id, state)


def _effective_session_id(session_id: str | None) -> str:
    return session_id or "default"


async def _citation_repair_if_needed(
    *,
    user_query: str,
    draft_answer: str,
    docs: list[RetrievedDoc],
    session_id: str,
    context_text: str,
) -> tuple[str, list[str], bool, str | None]:
    """
    Strict-mode reliability helper:
    - First pass: assess model output as-is.
    - If insufficient evidence in strict mode, run one bounded rewrite pass asking for explicit inline citations.
    - Never invent citations; only accept those matching retrieved doc IDs via policy enforcement.
    """
    first = enforce_citation_policy(draft_answer, docs, user_query)
    if first.verified:
        return first.answer, first.valid_citations, first.verified, first.reason

    if os.getenv("CITATION_MODE", "strict").lower() != "strict":
        return first.answer, first.valid_citations, first.verified, first.reason
    if not docs:
        return first.answer, first.valid_citations, first.verified, first.reason

    allowed_ids = ", ".join(str(d.doc_id) for d in docs)
    repair_messages = _build_claude_messages(
        session_id=session_id,
        user_message=(
            "Rewrite your previous answer using ONLY the retrieved context. "
            "Add an inline citation [doc:<id>] to every factual sentence. "
            f"Allowed doc ids: {allowed_ids}. "
            f"Original user question: {user_query}\n"
            f"Previous draft answer:\n{draft_answer}"
        ),
        context_json=context_text,
    )
    try:
        repaired = await claude.create(system=SYSTEM_PROMPT, messages=repair_messages)
    except Exception:
        # Fall back to the first strict assessment result.
        return first.answer, first.valid_citations, first.verified, first.reason

    second = enforce_citation_policy(repaired.text, docs, user_query)
    return second.answer, second.valid_citations, second.verified, second.reason


@app.post("/chat")
async def chat(req: ChatReq, auth: AuthContext = Depends(require_auth)) -> dict[str, Any]:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    session_id = _effective_session_id(req.session_id)
    started = time.time()
    docs = _build_retrieval_docs(req.message, req.doc_type, int(os.getenv("RAG_TOP_K", "8")))
    built = build_retrieval_context(
        docs,
        max_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000")),
        snippet_chars=int(os.getenv("RAG_SNIPPET_CHARS", "400")),
    )
    messages = _build_claude_messages(session_id, req.message, built.context_text)
    prompt_hash = build_prompt_hash(SYSTEM_PROMPT, built.context_text, maybe_redact(req.message))

    try:
        response = await claude.create(system=SYSTEM_PROMPT, messages=messages)
    except TimeoutError:
        raise HTTPException(status_code=504, detail="Model request timed out. Please retry with a narrower question.")

    answer, citations, verified, reason = await _citation_repair_if_needed(
        user_query=req.message,
        draft_answer=response.text,
        docs=built.included_docs,
        session_id=session_id,
        context_text=built.context_text,
    )
    _update_session(session_id, req.message, answer, citations)
    latency_s = time.time() - started
    metrics.observe(latency_s, response.input_tokens, response.output_tokens)
    insert_audit_log(
        AuditRecord(
            session_id=session_id,
            user_id=auth.user_id,
            endpoint="/chat",
            model=response.model,
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "gemini"),
            retrieved_doc_ids=[doc.doc_id for doc in built.included_docs],
            cited_doc_ids=[int(c.split(":")[1]) for c in citations if ":" in c],
            latency_ms=round(latency_s * 1000, 2),
            tokens_in=response.input_tokens,
            tokens_out=response.output_tokens,
            prompt_hash=prompt_hash,
        )
    )

    return {
        "answer": answer,
        "citations": citations,
        "sources": _sources_for_citations(citations, built.included_docs),
        "retrieved_docs": [asdict(doc) for doc in built.included_docs],
        "model": response.model,
        "verification": "verified" if verified else (reason or "unverified"),
    }


@app.post("/chat/stream")
async def chat_stream(req: ChatReq, auth: AuthContext = Depends(require_auth)) -> StreamingResponse:
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY is not configured")

    session_id = _effective_session_id(req.session_id)
    started = time.time()
    docs = _build_retrieval_docs(req.message, req.doc_type, int(os.getenv("RAG_TOP_K", "8")))
    built = build_retrieval_context(
        docs,
        max_chars=int(os.getenv("RAG_MAX_CONTEXT_CHARS", "6000")),
        snippet_chars=int(os.getenv("RAG_SNIPPET_CHARS", "400")),
    )
    messages = _build_claude_messages(session_id, req.message, built.context_text)
    prompt_hash = build_prompt_hash(SYSTEM_PROMPT, built.context_text, maybe_redact(req.message))

    async def event_gen():
        answer_text = ""
        input_tokens: int | None = None
        output_tokens: int | None = None
        model = ""
        try:
            yield _sse("meta", {"retrieved_docs": [asdict(d) for d in built.included_docs]})
            async for event in claude.stream(system=SYSTEM_PROMPT, messages=messages):
                if event["type"] == "token":
                    answer_text += event["token"]
                    model = event["model"]
                    yield _sse("token", {"delta": event["token"]})
                elif event["type"] == "done":
                    answer_text = event["text"]
                    input_tokens = event.get("input_tokens")
                    output_tokens = event.get("output_tokens")
                    model = event["model"]

            assessment = enforce_citation_policy(answer_text, built.included_docs, req.message)
            answer_text, citations = assessment.answer, assessment.valid_citations
            _update_session(session_id, req.message, answer_text, citations)
            latency_s = time.time() - started
            metrics.observe(latency_s, input_tokens, output_tokens)
            insert_audit_log(
                AuditRecord(
                    session_id=session_id,
                    user_id=auth.user_id,
                    endpoint="/chat/stream",
                    model=model,
                    embedding_provider=os.getenv("EMBEDDING_PROVIDER", "gemini"),
                    retrieved_doc_ids=[doc.doc_id for doc in built.included_docs],
                    cited_doc_ids=[int(c.split(":")[1]) for c in citations if ":" in c],
                    latency_ms=round(latency_s * 1000, 2),
                    tokens_in=input_tokens,
                    tokens_out=output_tokens,
                    prompt_hash=prompt_hash,
                )
            )
            yield _sse(
                "done",
                {
                    "answer": answer_text,
                    "citations": citations,
                    "sources": _sources_for_citations(citations, built.included_docs),
                    "retrieved_docs": [asdict(doc) for doc in built.included_docs],
                    "model": model,
                    "verification": "verified" if assessment.verified else (assessment.reason or "unverified"),
                },
            )
        except TimeoutError:
            yield _sse("error", {"error": "Model request timed out. Please retry with a narrower question."})
        except Exception as exc:
            yield _sse("error", {"error": str(exc)})

    return StreamingResponse(event_gen(), media_type="text/event-stream")


@app.get("/audit/recent")
def audit_recent(
    limit: int = 50,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
) -> dict[str, Any]:
    _ = authorize_audit_access(authorization=authorization, x_api_key=x_api_key)
    return {"results": get_recent_audit_logs(limit=limit)}
