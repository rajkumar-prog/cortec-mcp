"""
Chroma vector store — semantic search over stored memories.
"""

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings


class VectorStore:
    COLLECTION = "cortec_memories"

    def __init__(self, chroma_path: Path):
        chroma_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(
            path=str(chroma_path),
            settings=Settings(anonymized_telemetry=False),
        )
        self._col = self._client.get_or_create_collection(
            name=self.COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # ── Write ────────────────────────────────────────────────────────────────

    def add(
        self,
        memory_id: str,
        text: str,
        metadata: dict | None = None,
    ) -> None:
        self._col.upsert(
            ids=[memory_id],
            documents=[text],
            metadatas=[metadata or {}],
        )

    def delete(self, memory_id: str) -> None:
        self._col.delete(ids=[memory_id])

    # ── Read ─────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 5,
        project: str | None = None,
        type_: str | None = None,
    ) -> list[dict]:
        filters = []
        if project:
            filters.append({"project": project})
        if type_:
            filters.append({"type": type_})
        if len(filters) == 0:
            where = None
        elif len(filters) == 1:
            where = filters[0]
        else:
            where = {"$and": filters}
        results = self._col.query(
            query_texts=[query],
            n_results=min(top_k, max(1, self._col.count())),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        if not results["ids"] or not results["ids"][0]:
            return hits
        for i, memory_id in enumerate(results["ids"][0]):
            hits.append(
                {
                    "id": memory_id,
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": round(1 - results["distances"][0][i], 4),
                }
            )
        return hits

    def count(self) -> int:
        return self._col.count()
