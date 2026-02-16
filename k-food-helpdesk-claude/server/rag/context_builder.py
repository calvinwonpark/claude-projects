import json
from dataclasses import asdict, dataclass

from server.rag.retriever import RetrievedDoc


@dataclass
class ContextBuildResult:
    context_text: str
    included_docs: list[RetrievedDoc]


def build_retrieval_context(
    docs: list[RetrievedDoc],
    *,
    max_chars: int,
    snippet_chars: int = 400,
) -> ContextBuildResult:
    """Build structured retrieval context with explicit budget control."""
    included: list[RetrievedDoc] = []
    payload: list[dict] = []
    size = 0

    for doc in docs:
        doc_payload = {
            "doc_id": doc.doc_id,
            "title": doc.title,
            "source": doc.source,
            "chunk_index": doc.chunk_index,
            "content_snippet": doc.content_snippet[:snippet_chars],
            "score": round(doc.score, 6),
            "doc_type": doc.doc_type,
        }
        candidate_json = json.dumps(doc_payload, ensure_ascii=False)
        if size + len(candidate_json) > max_chars:
            break
        payload.append(doc_payload)
        included.append(
            RetrievedDoc(
                **{
                    **asdict(doc),
                    "content_snippet": doc_payload["content_snippet"],
                }
            )
        )
        size += len(candidate_json)

    context = json.dumps(payload, ensure_ascii=False, indent=2)
    return ContextBuildResult(context_text=context, included_docs=included)
