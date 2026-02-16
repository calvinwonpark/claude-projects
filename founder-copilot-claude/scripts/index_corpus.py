import hashlib
import os
import re
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db
from app.providers.embeddings import build_embeddings_provider


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(text: str, target_chars: int = 2800, overlap_chars: int = 450) -> list[str]:
    clean = (text or "").strip()
    if not clean:
        return []
    chunks = []
    start = 0
    n = len(clean)
    while start < n:
        end = min(start + target_chars, n)
        chunk = clean[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return chunks


def extract_title(path: Path, text: str) -> str:
    for line in text.splitlines()[:10]:
        if line.strip().startswith("#"):
            return line.lstrip("#").strip()[:200]
    return path.stem.replace("_", " ").title()[:200]


def normalize_doc_id(path: Path) -> str:
    return str(path).replace("\\", "/")


def iter_files(data_dir: Path):
    for path in sorted(data_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".csv"}:
            continue
        yield path


def main():
    provider = build_embeddings_provider()
    data_dir = ROOT / "data"
    files = list(iter_files(data_dir))
    total_chunks = 0
    inserted = 0
    skipped_existing = 0

    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            continue
        title = extract_title(path, text)
        doc_id = normalize_doc_id(path.relative_to(data_dir))
        chunks = chunk_text(text)
        total_chunks += len(chunks)
        if not chunks:
            continue

        embeddings = provider.embed_texts(chunks)
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            chash = content_hash(chunk)
            if db.document_exists_by_hash(chash):
                skipped_existing += 1
                continue
            stable_chunk_id = hashlib.sha1(f"{path}:{idx}:{chash}".encode("utf-8")).hexdigest()[:16]
            metadata = {
                "chunk_id": stable_chunk_id,
                "source_path": str(path.relative_to(data_dir)),
            }
            db.insert_document(
                doc_id=doc_id,
                source=str(path.relative_to(data_dir)),
                title=title,
                chunk_index=idx,
                content=chunk,
                content_hash=chash,
                embedding=emb,
                metadata=metadata,
            )
            inserted += 1

    print(
        f"Index complete: files={len(files)} total_chunks={total_chunks} "
        f"inserted={inserted} skipped_existing={skipped_existing}"
    )


if __name__ == "__main__":
    main()
