from __future__ import annotations

import json
import logging

from app import config
from app.models.bug import NormalizedBug
from app.models.knowledge import KnowledgeResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are a senior debugging assistant. Your job is to produce a practical, \
structured debugging prompt that an engineer can paste directly into Cursor \
to start investigating a bug.

Rules:
- Ground your output strictly in the provided bug data and company knowledge docs.
- Do NOT invent systems, services, or file paths that were not mentioned in the context.
- Prioritize the most likely investigation paths based on the evidence.
- Preserve any constraints and risk considerations from the bug report.
- Output clean structured plain text only — no markdown fences, no commentary.
"""

_USER_TEMPLATE = """\
Generate a Cursor-ready debugging prompt for the following bug.

## Normalized Bug Data
{bug_json}

## Detected Domains
{domains}

## Matched Company Knowledge Docs
{knowledge_docs}

## Desired Output Format

You are debugging bug {{bug_id}} in our codebase.

BUG CONTEXT
- Title: ...
- Severity: ...
- Component: ...
- Environment: ...

SUMMARY
...

REPRO STEPS
1. ...
2. ...

EXPECTED BEHAVIOR
...

ACTUAL BEHAVIOR
...

MATCHED COMPANY KNOWLEDGE
- file: <path>
  key guidance: <condensed relevant guidance from that doc>
(repeat for each matched doc)

INVESTIGATION AREAS
- <ordered list of specific places to look, informed by the bug data and knowledge docs>

COMPANY DEBUGGING RULES
- First identify likely code path before changing code
- Explain root-cause hypothesis with evidence
- Prefer minimal safe fix
- Add or update regression tests
- Call out risks and assumptions

TASK
1. Inspect likely code paths
2. Form 2–3 root-cause hypotheses
3. Pick the most likely one
4. Propose a minimal fix
5. Suggest tests
6. Summarize risks
"""


def _format_knowledge_docs(knowledge: KnowledgeResult) -> str:
    if not knowledge.docs:
        return "(no matched docs)"
    parts: list[str] = []
    for doc in knowledge.docs:
        parts.append(f"### {doc.file_path}\n{doc.content}")
    return "\n\n".join(parts)


def _build_fallback_prompt(
    bug: NormalizedBug,
    domains: list[str],
    knowledge: KnowledgeResult,
) -> str:
    """Deterministic fallback when no API key is configured."""
    steps = "\n".join(f"{i}. {s}" for i, s in enumerate(bug.repro_steps, 1)) or "N/A"
    components = ", ".join(bug.component) or "N/A"

    doc_sections: list[str] = []
    for doc in knowledge.docs:
        lines = doc.content.strip().splitlines()
        preview = "\n".join(lines[:6])
        doc_sections.append(f"- file: {doc.file_path}\n  key guidance: {preview}")
    matched_knowledge = "\n".join(doc_sections) or "- (none)"

    return f"""\
You are debugging bug {bug.bug_id} in our codebase.

BUG CONTEXT
- Title: {bug.title}
- Severity: {bug.severity}
- Component: {components}
- Environment: {bug.environment}

SUMMARY
{bug.summary}

REPRO STEPS
{steps}

EXPECTED BEHAVIOR
{bug.expected_behavior or "N/A"}

ACTUAL BEHAVIOR
{bug.actual_behavior or "N/A"}

MATCHED COMPANY KNOWLEDGE
{matched_knowledge}

INVESTIGATION AREAS
- Review the components: {components}
- Check domain-specific guidance for: {", ".join(domains) or "general"}
- Examine error messages in actual behavior for stack trace clues

COMPANY DEBUGGING RULES
- First identify likely code path before changing code
- Explain root-cause hypothesis with evidence
- Prefer minimal safe fix
- Add or update regression tests
- Call out risks and assumptions

TASK
1. Inspect likely code paths
2. Form 2–3 root-cause hypotheses
3. Pick the most likely one
4. Propose a minimal fix
5. Suggest tests
6. Summarize risks"""


async def generate_cursor_prompt(
    bug: NormalizedBug,
    domains: list[str],
    knowledge: KnowledgeResult,
) -> str:
    if not config.ANTHROPIC_API_KEY:
        logger.warning(
            "ANTHROPIC_API_KEY not set — using deterministic fallback prompt builder"
        )
        return _build_fallback_prompt(bug, domains, knowledge)

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        user_message = _USER_TEMPLATE.format(
            bug_json=json.dumps(bug.model_dump(), indent=2),
            domains=", ".join(domains) if domains else "(none detected)",
            knowledge_docs=_format_knowledge_docs(knowledge),
        )

        response = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=4096,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        return response.content[0].text

    except Exception as exc:
        logger.error("Claude API call failed: %s — falling back to local builder", exc)
        return _build_fallback_prompt(bug, domains, knowledge)
