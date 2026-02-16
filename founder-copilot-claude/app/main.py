import asyncio
import csv
import hashlib
import io
import json
import logging
import math
import re
import time
from typing import Any

import redis.asyncio as redis
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.metrics import metrics
from app import db
from app.config import settings
from app.agent.runtime import run_agent_turn
from app.providers.claude_client import ClaudeClient
from app.providers.embeddings import build_embeddings_provider
from app.rag import RetrievedDoc, Retriever, apply_citation_mode, build_context
from app.router.router import route_query
from app.security import AuthContext, authorize_audit, maybe_redact, require_auth
from app.storage import append_audit_log, get_recent_audit_logs
from app.tools import allowed_tools_for_query

try:
    from fastapi_limiter import FastAPILimiter as _FastAPILimiter
    from fastapi_limiter.depends import RateLimiter as _RateLimiter

    FastAPILimiter = _FastAPILimiter
    RateLimiter = _RateLimiter
except Exception:
    class FastAPILimiter:  # type: ignore
        @staticmethod
        async def init(*args, **kwargs):
            return None

    class RateLimiter:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass

        async def __call__(self, request: Request, response: Response):
            _ = (request, response)
            return None

load_dotenv()
app = FastAPI(title="Founder Copilot Claude")
logger = logging.getLogger("founder_copilot")
logger.setLevel(getattr(logging, settings.logging.level.upper(), logging.INFO))

redis_client = None
embeddings = build_embeddings_provider()
retriever = Retriever(embeddings)
claude = ClaudeClient(
    api_key=settings.anthropic.api_key,
    primary_model=settings.anthropic.primary_model,
    fallback_model=settings.anthropic.fallback_model,
    extra_models=settings.anthropic.model_candidates,
    temperature=settings.anthropic.temperature,
    max_output_tokens=settings.anthropic.max_output_tokens,
    timeout_ms=settings.anthropic.request_timeout_ms,
)

SESSION_CANCEL: dict[str, asyncio.Event] = {}
SESSION_STATE: dict[str, dict[str, Any]] = {}

AGENT_SYSTEM_PROMPTS = {
    "tech": "You are TechAdvisor. Give pragmatic architecture and implementation guidance for startups.",
    "marketing": "You are MarketingAdvisor. Provide GTM, channel, and messaging recommendations.",
    "investor": (
        "You are InvestorAdvisor. Provide fundraising, KPI, and investor narrative advice.\n"
        "Prefer investor/*.md sources for investor guidance.\n"
        "Use tech/*.md only when the user explicitly asks for technical differentiation or a technical slide.\n"
        "Do not cite tech/api/security docs for GTM, Team, or Ask sections."
    ),
}


def _client_ip(req: Request) -> str:
    return req.client.host if req.client else "unknown"


async def _session_id(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return _client_ip(req)


def _prompt_hash(*parts: str) -> str:
    return hashlib.sha256("\n---\n".join(parts).encode("utf-8")).hexdigest()


def _log_json(payload: dict[str, Any]) -> None:
    logger.info(json.dumps(payload, ensure_ascii=False))


def _sources_for_citations(citations: list[str], docs: list[Any]) -> list[dict[str, str]]:
    id_to_doc = {str(d.doc_id): d for d in docs}
    out = []
    seen = set()
    for c in citations:
        doc_id = c.split(":", 1)[1] if ":" in c else ""
        d = id_to_doc.get(doc_id)
        if d and d.doc_id not in seen:
            seen.add(d.doc_id)
            out.append({"file_id": f"doc-{d.doc_id}", "filename": d.source, "quote": d.content[:250]})
    return out


def _is_affirmation(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in {"yes", "y", "ok", "okay", "sure", "sounds good", "go ahead", "네", "응", "예"}


def _deterministic_grounded_fallback(user_msg: str, docs: list[Any]) -> tuple[str, list[str], str]:
    _ = user_msg
    if not docs:
        msg = (
            "I do not have enough evidence in retrieved sources to answer reliably. "
            "Could you clarify your request or provide a relevant document?"
        )
        return msg, [], "insufficient_evidence"

    primary = docs[0]
    citation = f"doc:{primary.doc_id}"
    lines = [ln.strip() for ln in str(primary.content).splitlines() if ln.strip()]
    bullets: list[str] = []
    for ln in lines:
        cleaned = ln.lstrip("-*0123456789. ").strip()
        if len(cleaned) < 12:
            continue
        bullets.append(cleaned)
        if len(bullets) >= 4:
            break
    if not bullets:
        sentences = [s.strip() for s in re.split(r"[.!?]\s+", str(primary.content)) if s.strip()]
        bullets = sentences[:3] or ["Use the retrieved source to build a concrete step-by-step plan."]

    answer = "Based on retrieved sources, here is a practical plan:\n\n"
    for i, b in enumerate(bullets[:4], start=1):
        answer += f"{i}. {b} [{citation}]\n"
    answer += f"\nIf helpful, I can convert this into a 2-week execution checklist [{citation}]."
    return answer.strip(), [citation], "verified"


def _is_pitch_deck_query(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in ["pitch deck", "pre-seed deck", "seed deck", "investor deck"])


def _build_agent_system_prompt(selected_agent: str, user_msg: str) -> str:
    base = AGENT_SYSTEM_PROMPTS.get(selected_agent, AGENT_SYSTEM_PROMPTS["tech"])
    common = (
        "\nUse only retrieved context for factual statements. "
        "Add inline citations like [doc:<doc_id>] for grounded claims."
    )
    if selected_agent != "investor":
        return base + common
    investor_specific = (
        "\nIf tool intent is ambiguous, ask: "
        "\"Would you like help estimating TAM or unit economics?\" instead of calling tools."
    )
    if _is_pitch_deck_query(user_msg):
        return (
            base
            + common
            + investor_specific
            + "\nFor pitch deck outline responses, return JSON only with this exact shape:"
            + '\n{"slides":[{"number":1,"title":"Problem","description":"...","citations":["doc:<id>"]}]}'
            + "\nEnsure slides are complete and ordered from 1..N."
        )
    return base + common + investor_specific


def _allow_tech_citations_for_investor(query: str) -> bool:
    q = (query or "").lower()
    return any(k in q for k in ["technical slide", "technical differentiation", "architecture slide", "tech moat"])


def _normalize_doc_citation(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    if v.startswith("doc:"):
        return v
    return f"doc:{v}"


def _format_investor_slides_if_json(answer: str) -> str:
    raw = (answer or "").strip()
    if not raw:
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return raw
    try:
        obj = json.loads(raw[start : end + 1])
    except Exception:
        return raw
    slides = obj.get("slides")
    if not isinstance(slides, list) or not slides:
        return raw
    out_lines = []
    ordered = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        ordered.append(s)
    if not ordered:
        return raw
    for idx, s in enumerate(ordered, start=1):
        title = str(s.get("title") or f"Slide {idx}").strip()
        desc = str(s.get("description") or "").strip()
        cits = s.get("citations") or []
        norm_cits = []
        if isinstance(cits, list):
            for c in cits:
                cc = _normalize_doc_citation(str(c))
                if cc:
                    norm_cits.append(cc)
        cite_text = (" " + " ".join(f"[{c}]" for c in norm_cits)) if norm_cits else ""
        out_lines.append(f"{idx}. **{title}**: {desc}{cite_text}".strip())
    return "\n\n".join(out_lines)


def _filter_citations_for_alignment(
    citations: list[str],
    docs: list[Any],
    selected_agent: str,
    query: str,
) -> list[str]:
    if selected_agent != "investor":
        return citations
    allow_tech = _allow_tech_citations_for_investor(query)
    id_to_source = {f"doc:{str(d.doc_id)}": str(getattr(d, "source", "")) for d in docs}
    filtered = []
    for c in citations:
        src = id_to_source.get(c, "")
        if src.startswith("upload:"):
            filtered.append(c)
            continue
        if src.startswith("investor/"):
            filtered.append(c)
            continue
        if allow_tech and src.startswith("tech/"):
            filtered.append(c)
            continue
    # Preserve order and dedupe.
    out = []
    seen = set()
    for c in filtered:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _strip_unaligned_citations(answer: str, allowed_citations: list[str]) -> str:
    allowed = set(allowed_citations)

    def _replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return f"[{token}]" if token in allowed else ""

    text = re.sub(r"\[(doc:[^\]]+)\]", _replace, answer or "")
    # Compact extra spaces introduced by removed citation tokens.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def _dedupe_inline_citations(answer: str) -> str:
    lines = (answer or "").splitlines()
    out: list[str] = []
    for line in lines:
        seen: set[str] = set()

        def _replace(match: re.Match[str]) -> str:
            token = match.group(1)
            if token in seen:
                return ""
            seen.add(token)
            return f"[{token}]"

        deduped = re.sub(r"\[(doc:[^\]]+)\]", _replace, line)
        deduped = re.sub(r"[ \t]{2,}", " ", deduped).strip()
        out.append(deduped)
    return "\n".join(out).strip()


def _verification_from_tool_results(
    verification: str,
    tool_results: list[dict[str, Any]],
) -> str:
    if not tool_results:
        return "not_applicable" if verification == "verified" else verification
    joined = json.dumps(tool_results, ensure_ascii=False).lower()
    has_stub_marker = ("stubbed estimate" in joined) or ("stubbed" in joined) or ("demo" in joined)
    hardcoded_stub_tools = any(tr.get("name") in {"market_size_lookup", "competitor_summary"} for tr in tool_results)
    if has_stub_marker or hardcoded_stub_tools:
        return "demo_mode"
    return verification


def _safe_upload_doc_id(filename: str, idx: int) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", (filename or f"file_{idx}")).strip("_")
    if not base:
        base = f"file_{idx}"
    return f"upload/{base}"


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


async def _summarize_uploaded_files(files: list[UploadFile] | None) -> list[RetrievedDoc]:
    out: list[RetrievedDoc] = []
    if not files:
        return out
    for idx, up in enumerate(files):
        try:
            raw = await up.read()
            text = raw.decode("utf-8", errors="ignore")
            fname = up.filename or f"upload_{idx}.txt"
            doc_id = _safe_upload_doc_id(fname, idx)
            summary = ""
            if fname.lower().endswith(".csv"):
                reader = csv.DictReader(io.StringIO(text))
                rows = []
                for i, row in enumerate(reader):
                    if i >= 200:
                        break
                    rows.append(row)
                cols = reader.fieldnames or []
                numeric_stats: dict[str, dict[str, float]] = {}
                for c in cols:
                    nums = []
                    for r in rows:
                        v = str(r.get(c, "")).strip().replace(",", "")
                        if not v:
                            continue
                        try:
                            nums.append(float(v))
                        except ValueError:
                            continue
                    if nums:
                        numeric_stats[c] = {
                            "count": float(len(nums)),
                            "min": min(nums),
                            "max": max(nums),
                            "avg": round(sum(nums) / len(nums), 6),
                        }
                sample_rows = rows[:3]
                chart_rows = rows[:50]
                summary = json.dumps(
                    {
                        "type": "csv_summary",
                        "filename": fname,
                        "row_count_sampled": len(rows),
                        "columns": cols,
                        "numeric_stats": numeric_stats,
                        "rows": chart_rows,
                        "sample_rows": sample_rows,
                    },
                    ensure_ascii=False,
                )[:6000]
            else:
                summary = text[:6000]
            out.append(
                RetrievedDoc(
                    doc_id=doc_id,
                    title=fname,
                    source=f"upload:{fname}",
                    chunk_index=0,
                    content=summary,
                    score=1.0,
                )
            )
        finally:
            try:
                await up.close()
            except Exception:
                pass
    return out


def _is_chart_request(text: str) -> bool:
    q = (text or "").lower()
    keys = ["chart", "bar chart", "plot", "graph", "visualize", "visualization", "draw", "kpi tracker"]
    return any(k in q for k in keys)


def _build_visualization_from_upload_docs(upload_docs: list[RetrievedDoc] | None) -> dict[str, Any] | None:
    if not upload_docs:
        return None
    for d in upload_docs:
        try:
            payload = json.loads(d.content)
        except Exception:
            continue
        if payload.get("type") != "csv_summary":
            continue
        cols = [str(c) for c in payload.get("columns", [])]
        rows = payload.get("rows", [])
        if not isinstance(rows, list) or not rows:
            continue
        metric_col = "Metric" if "Metric" in cols else (cols[0] if cols else "metric")
        target_col = "Target" if "Target" in cols else None
        actual_col = "Actual" if "Actual" in cols else None
        status_col = "Status" if "Status" in cols else None
        if not (target_col and actual_col):
            continue

        values = []
        for row in rows:
            metric = str(row.get(metric_col, "")).strip()
            target = _to_float(row.get(target_col))
            actual = _to_float(row.get(actual_col))
            if not metric or target is None or actual is None:
                continue
            status = str(row.get(status_col, "")).strip() if status_col else ""
            below_target = actual < target
            values.append(
                {
                    "metric": metric,
                    "series": "Target",
                    "value": target,
                    "below_target": below_target,
                    "status": status,
                }
            )
            values.append(
                {
                    "metric": metric,
                    "series": "Actual",
                    "value": actual,
                    "below_target": below_target,
                    "status": status,
                }
            )
        if not values:
            continue
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "description": "KPI tracker bar chart with below-target highlighting.",
            "data": {"values": values},
            "mark": {"type": "bar"},
            "encoding": {
                "x": {"field": "metric", "type": "nominal", "sort": None, "axis": {"labelAngle": -25}},
                "xOffset": {"field": "series"},
                "y": {"field": "value", "type": "quantitative"},
                "color": {
                    "condition": {
                        "test": "datum.series === 'Actual' && datum.below_target",
                        "value": "#ef4444",
                    },
                    "field": "series",
                    "type": "nominal",
                    "scale": {"domain": ["Target", "Actual"], "range": ["#6366f1", "#22c55e"]},
                },
                "tooltip": [
                    {"field": "metric", "type": "nominal"},
                    {"field": "series", "type": "nominal"},
                    {"field": "value", "type": "quantitative"},
                    {"field": "status", "type": "nominal"},
                ],
            },
        }
        return {"format": "vega_lite", "title": "KPI Tracker: Target vs Actual", "spec": spec}
    return None


def _chart_summary_from_visualization(visualization: dict[str, Any]) -> str:
    try:
        values = visualization.get("spec", {}).get("data", {}).get("values", [])
        if not isinstance(values, list):
            values = []
        actual_rows = [v for v in values if str(v.get("series", "")).lower() == "actual"]
        below = [v for v in actual_rows if bool(v.get("below_target"))]
        top = sorted(actual_rows, key=lambda x: float(x.get("value", 0.0)), reverse=True)[:3]
        top_names = ", ".join(str(x.get("metric", "")) for x in top if x.get("metric"))
        return (
            f"I rendered the KPI bar chart below (Target vs Actual) and highlighted below-target Actual bars in red.\n\n"
            f"- Metrics tracked: {len(actual_rows)}\n"
            f"- Below-target metrics: {len(below)}\n"
            f"- Highest Actual metrics: {top_names if top_names else 'n/a'}"
        )
    except Exception:
        return "I rendered the KPI bar chart below (Target vs Actual) and highlighted below-target Actual bars in red."


def _build_math_plot_from_query(query: str) -> tuple[str, dict[str, Any]] | None:
    q = (query or "").lower()
    if "plot" not in q and "graph" not in q and "draw" not in q:
        return None
    expr_match = re.search(r"y\s*=\s*x\s*\^\s*([0-9]+)", q)
    if not expr_match:
        expr_match = re.search(r"y\s*=\s*x\*\*\s*([0-9]+)", q)
    if not expr_match:
        return None
    power = int(expr_match.group(1))
    range_match = re.search(r"x\s*=\s*(-?\d+)\s*\.\.\s*(-?\d+)", q)
    x_start, x_end = 0, 10
    if range_match:
        x_start = int(range_match.group(1))
        x_end = int(range_match.group(2))
    if x_end < x_start:
        x_start, x_end = x_end, x_start
    if x_end - x_start > 200:
        x_end = x_start + 200
    values = []
    for x in range(x_start, x_end + 1):
        y = float(x**power)
        values.append({"x": x, "y": y})
    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "description": "Deterministic math plot generated from user query.",
        "data": {"values": values},
        "mark": {"type": "line", "point": True},
        "encoding": {
            "x": {"field": "x", "type": "quantitative"},
            "y": {"field": "y", "type": "quantitative"},
            "tooltip": [{"field": "x", "type": "quantitative"}, {"field": "y", "type": "quantitative"}],
        },
    }
    monotonic = "increases" if power >= 1 else "changes"
    curvature = "concave up" if power >= 2 else "linear"
    explanation = (
        f"Plotted y = x^{power} for x = {x_start}..{x_end}. "
        f"The curve is {curvature} and {monotonic} as x increases in this range. "
        f"For example: y({x_start}) = {x_start**power}, y({x_end}) = {x_end**power}."
    )
    return explanation, {"format": "vega_lite", "title": f"Plot: y = x^{power}", "spec": spec}


def _normalize_answer_for_visualization(answer: str, visualization: dict[str, Any] | None) -> str:
    if not visualization:
        return answer
    text = (answer or "").strip()
    lower = text.lower()
    blocked_phrases = [
        "i do not have the capability to generate graphs",
        "i do not have the capability to create graphical outputs",
        "i cannot generate graphs",
        "i cannot create visualizations",
        "without visualization capabilities",
    ]
    if any(p in lower for p in blocked_phrases):
        return (
            "I analyzed your uploaded KPI tracker and rendered a bar chart below.\n\n"
            "The chart compares Target vs Actual for each metric, and highlights below-target metrics in red."
        )
    if "rendered" not in lower and "chart below" not in lower:
        return text + "\n\n(Chart rendered below.)"
    return text


async def _repair_citations_if_needed(
    *,
    answer: str,
    docs: list[Any],
    user_msg: str,
    selected_agent: str,
) -> tuple[str, list[str], str]:
    fixed_answer, fixed_citations, fixed_verification = apply_citation_mode(answer, docs, user_msg)
    strict = settings.safety.citation_mode == "strict"
    if not strict or fixed_verification != "insufficient_evidence" or not docs:
        return fixed_answer, fixed_citations, fixed_verification

    allowed = ", ".join(f"[doc:{d.doc_id}]" for d in docs)
    repair_system = (
        _build_agent_system_prompt(selected_agent, user_msg)
        + "\nYou are revising a draft to satisfy strict grounding."
        + "\nKeep the same meaning and language."
        + "\nFor every factual paragraph, include at least one inline citation."
        + "\nUse only these citation ids: "
        + allowed
        + "\nDo not invent new citation ids."
    )
    repair_messages = [
        {"role": "user", "content": "User question:\n" + user_msg},
        {"role": "user", "content": "Retrieved context JSON:\n" + build_context(docs, max_chars=settings.retrieval.max_context_chars)},
        {"role": "user", "content": "Draft answer to revise with strict citations:\n" + answer},
    ]
    try:
        repaired = await claude.create(system=repair_system, messages=repair_messages, tools=[])
    except Exception:
        return _deterministic_grounded_fallback(user_msg, docs)
    repaired_answer, repaired_citations, repaired_verification = apply_citation_mode(repaired.text, docs, user_msg)
    if repaired_verification == "insufficient_evidence":
        return _deterministic_grounded_fallback(user_msg, docs)
    return repaired_answer, repaired_citations, repaired_verification


@app.on_event("startup")
async def startup() -> None:
    global redis_client
    redis_client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_client, identifier=_client_ip)
    db.ensure_schema()
    claude.warmup_model_selection()


@app.on_event("shutdown")
async def shutdown() -> None:
    global redis_client
    if redis_client:
        await redis_client.aclose()


@app.get("/")
def root():
    return FileResponse("app/static/index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/models")
def models(auth: AuthContext = Depends(require_auth)):
    _ = auth
    return claude.model_status()


@app.get("/api/metrics")
def api_metrics(auth: AuthContext = Depends(require_auth)):
    _ = auth
    return metrics.stats()


@app.post("/search", dependencies=[Depends(RateLimiter(times=30, seconds=60))])
async def search_docs(payload: dict[str, Any], auth: AuthContext = Depends(require_auth)):
    _ = auth
    query = str(payload.get("message") or payload.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "message required"}, status_code=400)
    top_k = int(payload.get("k") or settings.retrieval.top_k)
    docs, retrieval_ms = retriever.retrieve(query, top_k=top_k)
    return {
        "results": [
            {
                "doc_id": d.doc_id,
                "title": d.title,
                "source": d.source,
                "chunk_index": d.chunk_index,
                "content": d.content,
                "score": round(d.score, 6),
            }
            for d in docs
        ],
        "latency_ms": round(retrieval_ms, 2),
    }


@app.get("/metrics")
def metrics_page():
    return FileResponse("app/static/metrics.html")


@app.get("/audit/recent")
def audit_recent(
    limit: int = 50,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
):
    _ = authorize_audit(authorization, x_api_key)
    return {"results": get_recent_audit_logs(limit)}


@app.post("/chat", dependencies=[Depends(RateLimiter(times=10, seconds=60))])
async def chat_json(request: Request, payload: dict[str, Any], auth: AuthContext = Depends(require_auth)):
    session_id = str(payload.get("session_id") or await _session_id(request))
    user_msg = str(payload.get("message") or "").strip()
    if not user_msg:
        return JSONResponse({"error": "message required"}, status_code=400)
    final_payload: dict[str, Any] | None = None
    async for event in _run_chat(session_id=session_id, user_msg=user_msg, user_id=auth.user_id, stream=False):
        if event.get("type") == "json_result":
            final_payload = event.get("payload") or {}
        elif event.get("type") == "error":
            return JSONResponse({"error": str(event.get("error") or "unknown error")}, status_code=int(event.get("status_code") or 500))
    if final_payload is None:
        return JSONResponse({"error": "No response generated"}, status_code=500)
    return final_payload


@app.post("/chat/stream", dependencies=[Depends(RateLimiter(times=5, seconds=60))])
async def chat_stream(
    request: Request,
    message: str = Form(...),
    files: list[UploadFile] | None = File(default=None),
    auth: AuthContext = Depends(require_auth),
):
    session_id = await _session_id(request)
    user_msg = message.strip()
    if not user_msg:
        return JSONResponse({"error": "message required"}, status_code=400)

    upload_docs = await _summarize_uploaded_files(files)

    async def event_gen():
        async for evt in _run_chat(
            session_id=session_id,
            user_msg=user_msg,
            user_id=auth.user_id,
            stream=True,
            upload_docs=upload_docs,
        ):
            yield evt

    return StreamingResponse(event_gen(), media_type="text/event-stream")


async def _run_chat(
    session_id: str,
    user_msg: str,
    user_id: str | None,
    stream: bool,
    upload_docs: list[RetrievedDoc] | None = None,
):
    if not settings.anthropic.api_key:
        error = {"type": "error", "error": "ANTHROPIC_API_KEY missing", "status_code": 500}
        if stream:
            yield f"data: {json.dumps(error)}\n\n"
            return
        yield error
        return

    # Cancel previous generation for this session.
    prev = SESSION_CANCEL.get(session_id)
    if prev:
        prev.set()
    cancel_event = asyncio.Event()
    SESSION_CANCEL[session_id] = cancel_event

    started = time.time()
    session_state = SESSION_STATE.get(session_id, {})
    effective_user_msg = user_msg
    followup_note: str | None = None
    if (
        _is_affirmation(user_msg)
        and session_state.get("pending_clarification")
        and session_state.get("last_user_question")
    ):
        effective_user_msg = str(session_state["last_user_question"])
        followup_note = f"The user confirmed to continue previous question. Confirmation message: {user_msg}"

    route_started = time.time()
    routing_trace = route_query(effective_user_msg)
    route_ms = (time.time() - route_started) * 1000
    selected_agent = routing_trace["selected_agent"]
    agents_invoked = [selected_agent]
    if routing_trace.get("reviewer_agent"):
        agents_invoked.append(routing_trace["reviewer_agent"])

    retrieval_started = time.time()
    docs, retrieval_ms = retriever.retrieve(effective_user_msg, top_k=settings.retrieval.top_k)
    if upload_docs:
        docs = list(upload_docs) + docs
    context = build_context(docs, max_chars=settings.retrieval.max_context_chars)
    retrieval_elapsed = (time.time() - retrieval_started) * 1000

    chart_vis = _build_visualization_from_upload_docs(upload_docs) if _is_chart_request(effective_user_msg) else None
    if chart_vis is not None and upload_docs:
        answer = _chart_summary_from_visualization(chart_vis)
        citations = [f"doc:{upload_docs[0].doc_id}"]
        sources = _sources_for_citations(citations, docs)
        verification = "deterministic_computation"
        routing_trace["citations_used"] = citations
        routing_trace["tool_calls_made"] = []
        routing_trace["latency_ms_breakdown"] = {
            "routing": round(route_ms, 2),
            "retrieval": round(retrieval_elapsed, 2),
            "llm": 0.0,
        }
        routing_trace["agents_invoked"] = [selected_agent]
        routing_trace["agent_usage"] = [{"agent": selected_agent, "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0}]
        if stream:
            yield f"data: {json.dumps({'type': 'routing', 'routing_trace': routing_trace})}\n\n"
            yield f"data: {json.dumps({'type': 'text_delta', 'delta': answer, 'accumulated': answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done','answer': answer,'sources': sources,'citations': citations,'routing_trace': routing_trace,'verification': verification,'visualization': chart_vis})}\n\n"
        else:
            yield {
                "type": "json_result",
                "payload": {
                    "answer": answer,
                    "sources": sources,
                    "citations": citations,
                    "routing_trace": routing_trace,
                    "tool_results": [],
                    "verification": verification,
                    "visualization": chart_vis,
                },
            }
        total_ms = (time.time() - started) * 1000
        metrics.record(
            total_ms=total_ms,
            retrieval_ms=retrieval_ms,
            llm_ms=0.0,
            tokens_in=0,
            tokens_out=0,
            error=False,
        )
        SESSION_STATE[session_id] = {
            "last_user_question": effective_user_msg if not _is_affirmation(user_msg) else session_state.get("last_user_question", effective_user_msg),
            "pending_clarification": False,
            "last_verification": verification,
        }
        return

    math_plot = _build_math_plot_from_query(effective_user_msg)
    if math_plot is not None:
        final_answer, visualization = math_plot
        verification = "deterministic_computation"
        routing_trace["citations_used"] = []
        routing_trace["tool_calls_made"] = []
        routing_trace["latency_ms_breakdown"] = {
            "routing": round(route_ms, 2),
            "retrieval": round(retrieval_elapsed, 2),
            "llm": 0.0,
        }
        routing_trace["agents_invoked"] = [selected_agent]
        routing_trace["agent_usage"] = [{"agent": selected_agent, "latency_ms": 0.0, "tokens_in": 0, "tokens_out": 0}]
        if stream:
            yield f"data: {json.dumps({'type': 'routing', 'routing_trace': routing_trace})}\n\n"
            yield f"data: {json.dumps({'type': 'text_delta', 'delta': final_answer, 'accumulated': final_answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done','answer': final_answer,'sources': [],'citations': [],'routing_trace': routing_trace,'verification': verification,'visualization': visualization})}\n\n"
        else:
            yield {
                "type": "json_result",
                "payload": {
                    "answer": final_answer,
                    "sources": [],
                    "citations": [],
                    "routing_trace": routing_trace,
                    "tool_results": [],
                    "verification": verification,
                    "visualization": visualization,
                },
            }
        total_ms = (time.time() - started) * 1000
        metrics.record(
            total_ms=total_ms,
            retrieval_ms=retrieval_ms,
            llm_ms=0.0,
            tokens_in=0,
            tokens_out=0,
            error=False,
        )
        SESSION_STATE[session_id] = {
            "last_user_question": effective_user_msg if not _is_affirmation(user_msg) else session_state.get("last_user_question", effective_user_msg),
            "pending_clarification": False,
            "last_verification": verification,
        }
        return
    citations_used: list[str] = []
    sources: list[dict[str, str]] = []
    tool_results: list[dict[str, Any]] = []
    verification = "verified"

    system_prompt = _build_agent_system_prompt(selected_agent, effective_user_msg)
    messages = [
        {"role": "user", "content": "Retrieved context JSON:\n" + context},
        {"role": "user", "content": f"Routing selected agent: {selected_agent}"},
        {"role": "user", "content": effective_user_msg},
    ]
    if upload_docs:
        messages.insert(
            1,
            {
                "role": "user",
                "content": "Uploaded files are included in retrieved context. Use them for analysis/computation when relevant.",
            },
        )
    if followup_note:
        messages.insert(2, {"role": "user", "content": followup_note})
    llm_started = time.time()
    usage_in = 0
    usage_out = 0
    model_name = None
    request_id = None
    tool_calls_made: list[dict[str, Any]] = []
    strict_mode = settings.safety.citation_mode == "strict"
    strict_stream_buffered = settings.safety.strict_stream_buffered

    if stream:
        yield f"data: {json.dumps({'type': 'routing', 'routing_trace': routing_trace})}\n\n"
        yield f"data: {json.dumps({'type': 'status', 'message': 'Running agent runtime...'})}\n\n"

    runtime_result = await run_agent_turn(
        claude=claude,
        system_prompt=system_prompt,
        messages=messages,
        tools=allowed_tools_for_query(effective_user_msg),
        cancel_event=cancel_event,
    )
    model_name = runtime_result.model
    request_id = runtime_result.request_id
    usage_in = runtime_result.usage_in
    usage_out = runtime_result.usage_out
    tool_calls_made = runtime_result.tool_calls
    tool_results = runtime_result.tool_results

    if stream:
        for evt in runtime_result.status_events:
            yield f"data: {json.dumps(evt)}\n\n"

    draft_answer = runtime_result.final_text
    if selected_agent == "investor" and _is_pitch_deck_query(effective_user_msg):
        draft_answer = _format_investor_slides_if_json(draft_answer)
    final_answer, citations_used, verification = await _repair_citations_if_needed(
        answer=draft_answer,
        docs=docs,
        user_msg=effective_user_msg,
        selected_agent=selected_agent,
    )
    citations_used = _filter_citations_for_alignment(citations_used, docs, selected_agent, effective_user_msg)
    final_answer = _strip_unaligned_citations(final_answer, citations_used)
    final_answer = _dedupe_inline_citations(final_answer)
    sources = _sources_for_citations(citations_used, docs)
    routing_trace["citations_used"] = citations_used
    routing_trace["tool_calls_made"] = list(dict.fromkeys([tc.get("name") for tc in tool_calls_made]))
    routing_trace["tool_results_made"] = tool_results
    routing_trace["latency_ms_breakdown"] = {
        "routing": round(route_ms, 2),
        "retrieval": round(retrieval_elapsed, 2),
        "llm": round((time.time() - llm_started) * 1000, 2),
    }
    routing_trace["agents_invoked"] = agents_invoked
    routing_trace["agent_usage"] = [
        {"agent": agent, "latency_ms": round((time.time() - llm_started) * 1000, 2), "tokens_in": usage_in, "tokens_out": usage_out}
        for agent in agents_invoked
    ]
    visualization = _build_visualization_from_upload_docs(upload_docs) if _is_chart_request(effective_user_msg) else None
    final_answer = _normalize_answer_for_visualization(final_answer, visualization)
    verification = _verification_from_tool_results(verification, tool_results)

    if stream:
        if strict_mode and strict_stream_buffered:
            yield f"data: {json.dumps({'type': 'text_delta', 'delta': final_answer, 'accumulated': final_answer})}\n\n"
        yield f"data: {json.dumps({'type': 'done','answer': final_answer,'sources': sources,'citations': citations_used,'routing_trace': routing_trace,'verification': verification,'visualization': visualization,'tool_results': tool_results})}\n\n"
    else:
        yield {
            "type": "json_result",
            "payload": {
                "answer": final_answer,
                "sources": sources,
                "citations": citations_used,
                "routing_trace": routing_trace,
                "tool_results": tool_results,
                "verification": verification,
                "visualization": visualization,
            },
        }

    total_ms = (time.time() - started) * 1000
    metrics.record(
        total_ms=total_ms,
        retrieval_ms=retrieval_ms,
        llm_ms=(time.time() - llm_started) * 1000,
        tokens_in=usage_in,
        tokens_out=usage_out,
        error=False,
    )

    audit_row = {
        "timestamp": int(time.time() * 1000),
        "session_id": session_id,
        "user_id": user_id,
        "endpoint": "/chat/stream" if stream else "/chat",
        "model": model_name,
        "selected_agent": selected_agent,
        "retrieved_doc_ids": [d.doc_id for d in docs],
        "cited_doc_ids": [c.split(":", 1)[1] for c in citations_used if ":" in c],
        "latency_ms": round(total_ms, 2),
        "tokens_in": usage_in,
        "tokens_out": usage_out,
        "request_id": request_id,
        "prompt_hash": _prompt_hash(system_prompt, context, maybe_redact(user_msg)),
        "tool_calls": tool_calls_made,
        "tool_results": tool_results,
    }
    audit_row["embedding_provider"] = settings.embedding_provider
    if settings.logging.enable_audit_logs:
        append_audit_log(audit_row)
    _log_json(
        {
            "session_id": session_id,
            "user_id": user_id,
            "selected_agent": selected_agent,
            "model": model_name,
            "tokens_in": usage_in,
            "tokens_out": usage_out,
            "citations": citations_used,
            "latency_ms": round(total_ms, 2),
            "latency_breakdown": routing_trace.get("latency_ms_breakdown", {}),
            "request_id": request_id,
        }
    )
    SESSION_STATE[session_id] = {
        "last_user_question": effective_user_msg if not _is_affirmation(user_msg) else session_state.get("last_user_question", effective_user_msg),
        "pending_clarification": verification == "insufficient_evidence",
        "last_verification": verification,
    }


# Keep endpoint parity with legacy reset behavior.
@app.post("/reset")
async def reset():
    SESSION_CANCEL.clear()
    SESSION_STATE.clear()
    return {"message": "session reset"}
