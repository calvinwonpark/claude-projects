import glob
import json
import os
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Ensure repo root is importable when executing as a script.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.providers.embeddings import build_embeddings_provider

load_dotenv()


def _conn():
    return psycopg2.connect(
        host=os.getenv("PGHOST", "db"),
        port=int(os.getenv("PGPORT", "5432")),
        dbname=os.getenv("PGDATABASE", "helpdesk"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
    )


def _chunks(text: str, size: int) -> Iterable[str]:
    text = (text or "").strip()
    for i in range(0, len(text), size):
        chunk = text[i : i + size].strip()
        if chunk:
            yield chunk


def _insert_doc(
    cur,
    *,
    source: str,
    title: str,
    doc_type: str,
    chunk_index: int,
    content: str,
    embedding: list[float],
    meta: dict,
) -> None:
    cur.execute(
        """
        INSERT INTO docs (source, title, doc_type, chunk_index, content, embedding, meta)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        """,
        (source, title, doc_type, chunk_index, content, embedding, json.dumps(meta)),
    )


def ingest_policies(cur, embedder) -> int:
    count = 0
    for path in sorted(glob.glob("data/policies/*.md")):
        source = os.path.basename(path)
        title = source.replace(".md", "").replace("_", " ").title()
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        parts = list(_chunks(raw, size=800))
        if not parts:
            continue
        vectors = embedder.embed_texts(parts)
        for idx, (content, embedding) in enumerate(zip(parts, vectors)):
            _insert_doc(
                cur,
                source=source,
                title=title,
                doc_type="policy",
                chunk_index=idx,
                content=content,
                embedding=embedding,
                meta={"doc_type": "policy", "chunk_index": idx, "source_path": path},
            )
            count += 1
    return count


def ingest_restaurants(cur, embedder, csv_path: str = "data/policies/restaurants.csv") -> int:
    if not os.path.exists(csv_path):
        return 0
    count = 0
    df = pd.read_csv(csv_path).fillna("")
    for row_idx, row in df.iterrows():
        text = (
            f"Restaurant: {row.get('name', '')}\n"
            f"District: {row.get('district', '')}\n"
            f"Categories: {row.get('categories', '')}\n"
            f"Hours: {row.get('hours', '')}\n"
            f"Delivery Area: {row.get('delivery_area', '')}\n"
            f"Allergens: {row.get('allergens', '')}\n"
            f"Notes: {row.get('notes', '')}\n"
        )
        chunks = list(_chunks(text, size=600))
        vectors = embedder.embed_texts(chunks)
        for chunk_idx, (content, embedding) in enumerate(zip(chunks, vectors)):
            _insert_doc(
                cur,
                source="restaurants.csv",
                title=str(row.get("name", f"restaurant-{row_idx}")),
                doc_type="restaurant",
                chunk_index=chunk_idx,
                content=content,
                embedding=embedding,
                meta={"doc_type": "restaurant", "row_index": int(row_idx), "chunk_index": chunk_idx},
            )
            count += 1
    return count


def main() -> None:
    embedder = build_embeddings_provider()
    expected_dim = int(os.getenv("EMBEDDING_DIM", "768"))
    if getattr(embedder, "dimension", expected_dim) != expected_dim:
        raise ValueError("Embedding provider dimension does not match EMBEDDING_DIM")

    with _conn() as con, con.cursor() as cur:
        cur.execute("TRUNCATE TABLE docs RESTART IDENTITY")
        policy_count = ingest_policies(cur, embedder)
        restaurant_count = ingest_restaurants(cur, embedder)
        con.commit()

    print(f"Ingest complete. policy_chunks={policy_count}, restaurant_chunks={restaurant_count}")


if __name__ == "__main__":
    main()
