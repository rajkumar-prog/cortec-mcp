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
        """Initialise the store and create the database schema if it does not exist."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        """Open and return a new SQLite connection with row_factory set."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self):
        """Create tables, indexes, and run any pending column migrations."""
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
                    raw_text      TEXT,
                    commit_sha    TEXT,
                    so_url        TEXT
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
            # Migrate existing databases — add columns added after initial schema
            cols = {row[1] for row in conn.execute("PRAGMA table_info(memories)")}
            if "commit_sha" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN commit_sha TEXT")
            if "so_url" not in cols:
                conn.execute("ALTER TABLE memories ADD COLUMN so_url TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_commit_sha ON memories(commit_sha)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_so_url ON memories(so_url)"
            )

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
        commit_sha: str | None = None,
        so_url: str | None = None,
    ) -> str:
        """Insert a new memory record and return its generated ID."""
        memory_id = str(uuid.uuid4())[:8]
        now = datetime.now(timezone.utc).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memories
                  (id, project, type, summary, source, created_at,
                   confidence, tags, related_files, approved, raw_text, commit_sha, so_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id, project, type_, summary, source, now,
                    confidence,
                    json.dumps(tags or []),
                    json.dumps(related_files or []),
                    int(approved),
                    raw_text,
                    commit_sha,
                    so_url,
                ),
            )
        return memory_id

    def get_by_so_url(self, so_url: str) -> dict | None:
        """Return a memory stored from a specific Stack Overflow URL."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE so_url = ?", (so_url,)
            ).fetchone()
        return dict(row) if row else None

    def link_to_commit(self, memory_id: str, commit_sha: str) -> bool:
        """Attach a commit SHA to an existing memory."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memories SET commit_sha = ? WHERE id = ?",
                (commit_sha, memory_id),
            )
        return cur.rowcount > 0

    def get_by_commit(self, commit_sha: str) -> list[dict]:
        """Return all memories linked to a specific commit SHA."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE commit_sha = ?", (commit_sha,)
            ).fetchall()
        return [dict(r) for r in rows]

    def approve(self, memory_id: str) -> bool:
        """Mark a memory as approved. Returns True if the record was found and updated."""
        with self._conn() as conn:
            cur = conn.execute(
                "UPDATE memories SET approved = 1 WHERE id = ?", (memory_id,)
            )
        return cur.rowcount > 0

    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Returns True if a record was removed."""
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        return cur.rowcount > 0

    def get(self, memory_id: str) -> dict | None:
        """Fetch a single memory by ID, or None if not found."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            ).fetchone()
        return dict(row) if row else None

    def list_all(self, project: str | None = None, approved_only: bool = True) -> list[dict]:
        """Return all memories, optionally filtered by project and approval state."""
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
        """Return memories that have not been approved yet."""
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
        """Return total, pending, approved, and project-scoped memory counts."""
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
        """Record a conflict for memory_id_a and return the new conflict ID."""
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
        """Return conflicts filtered by resolved state (default: unresolved)."""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM conflicts WHERE resolved = ?", (int(resolved),)
            ).fetchall()
        return [dict(r) for r in rows]
