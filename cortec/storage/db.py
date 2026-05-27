"""
SQLite metadata store — manages memory records, conflicts, and pending approvals.
"""

import sqlite3
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path


class MetadataStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id            TEXT PRIMARY KEY,
                    project       TEXT NOT NULL DEFAULT 'default',
                    type          TEXT NOT NULL DEFAULT 'general',
                    summary       TEXT NOT NULL,
                    source        TEXT,
                    created_at    TEXT NOT NULL,
                    confidence    REAL NOT NULL DEFAULT 0.5,
                    tags          TEXT NOT NULL DEFAULT '[]',
                    related_files TEXT NOT NULL DEFAULT '[]',
                    conflict_flag INTEGER NOT NULL DEFAULT 0,
                    approved      INTEGER NOT NULL DEFAULT 0,
                    raw_text      TEXT
                );

                CREATE TABLE IF NOT EXISTS conflicts (
                    id           TEXT PRIMARY KEY,
                    memory_id_a  TEXT NOT NULL,
                    description  TEXT NOT NULL,
                    detected_at  TEXT NOT NULL,
                    resolved     INTEGER NOT NULL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_memories_project  ON memories(project);
                CREATE INDEX IF NOT EXISTS idx_memories_type     ON memories(type);
                CREATE INDEX IF NOT EXISTS idx_memories_approved ON memories(approved);
            """)

    def insert(
        self,
        summary: str,
        project: str = "default",
        type_: str = "general",
        source: str = "session",
        confidence: float = 0.5,
        tags: list[str] | None = None,
        related_files: list[str] | None = None,
        approved: bool = False,
        raw_text: str | None = None,
    ) -> str:
        memory_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memories
                  (id, project, type, summary, source, created_at,
                   confidence, tags, related_files, approved, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id, project, type_, summary, source, now,
                    confidence,
                    json.dumps(tags or []),
                    json.dumps(related_files or []),
                    int(approved),
                    raw_text,
                ),
            )
        return memory_id

    def approve(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memories SET approved = 1 WHERE id = ?", (memory_id,)
            )
        return cur.rowcount > 0

    def delete(self, memory_id: str) -> bool:
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def get(self, memory_id: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self, project: str | None = None, approved_only: bool = True) -> list[dict]:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list = []
        if project:
            query += " AND project = ?"
            params.append(project)
        if approved_only:
            query += " AND approved = 1"
        query += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def list_pending(self, project: str | None = None) -> list[dict]:
        query = "SELECT * FROM memories WHERE approved = 0"
        params: list = []
        if project:
            query += " AND project = ?"
            params.append(project)
        query += " ORDER BY created_at DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def count(self, project: str | None = None) -> dict:
        with self._conn() as conn:
            base = "SELECT COUNT(*) FROM memories"
            total = conn.execute(base).fetchone()[0]
            pending = conn.execute(base + " WHERE approved = 0").fetchone()[0]
            if project:
                proj_total = conn.execute(
                    base + " WHERE project = ?", (project,)
                ).fetchone()[0]
            else:
                proj_total = total
        return {
            "total": total,
            "pending": pending,
            "approved": total - pending,
            "project_total": proj_total,
        }

    def flag_conflict(self, memory_id_a: str, description: str) -> str:
        conflict_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE memories SET conflict_flag = 1 WHERE id = ?",
                (memory_id_a,),
            )
            conn.execute(
                "INSERT INTO conflicts (id, memory_id_a, description, detected_at) VALUES (?, ?, ?, ?)",
                (conflict_id, memory_id_a, description, now),
            )
        return conflict_id

    def list_conflicts(self, resolved: bool = False) -> list[dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conflicts WHERE resolved = ?", (int(resolved),)
            ).fetchall()
        return [dict(r) for r in rows]
