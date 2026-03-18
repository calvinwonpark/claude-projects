from __future__ import annotations

from pathlib import Path

from app.models.knowledge import KnowledgeDoc, KnowledgeResult
from app.services.company_knowledge import DOMAIN_DOC_MAP

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_doc(file_path: str) -> KnowledgeDoc | None:
    abs_path = _PROJECT_ROOT / file_path
    try:
        content = abs_path.read_text(encoding="utf-8")
        return KnowledgeDoc(file_path=file_path, content=content)
    except FileNotFoundError:
        return None


def load_knowledge(domains: list[str]) -> KnowledgeResult:
    seen: set[str] = set()
    file_paths: list[str] = []

    for domain in domains:
        for p in DOMAIN_DOC_MAP.get(domain, []):
            if p not in seen:
                seen.add(p)
                file_paths.append(p)

    docs = [d for p in file_paths if (d := _load_doc(p)) is not None]
    return KnowledgeResult(domains=domains, docs=docs)
