from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.services.jira_client import get_jira_bug
from app.services.normalize_bug import normalize_bug
from app.services.detect_domain import detect_domains
from app.services.load_knowledge import load_knowledge
from app.services.claude_prompt_generator import generate_cursor_prompt

app = FastAPI(title="Jira Bug → Cursor Prompt")

_TEMPLATE_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATE_DIR))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


class GenerateRequest(BaseModel):
    issue_key: str


@app.post("/generate")
async def generate(body: GenerateRequest):
    issue_key = body.issue_key.strip().upper()
    if not issue_key:
        raise HTTPException(status_code=400, detail="issue_key is required")

    try:
        raw_bug = await get_jira_bug(issue_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))

    normalized = normalize_bug(raw_bug)
    domains = detect_domains(normalized)
    knowledge = load_knowledge(domains)
    prompt = await generate_cursor_prompt(normalized, domains, knowledge)

    return {
        "raw_bug": raw_bug.model_dump(),
        "normalized_bug": normalized.model_dump(),
        "detected_domains": domains,
        "matched_docs": [d.model_dump() for d in knowledge.docs],
        "generated_prompt": prompt,
    }
