"""
SQLite-backed metadata store.
Tracks which files have been indexed and their content hashes,
so we only re-index files that actually changed.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Optional

from synapse.config import METADATA_PATH


# ── Schema ────────────────────────────────────────────────────────────────────

CREATE_FILES_TABLE = """
CREATE TABLE IF NOT EXISTS indexed_files (
    file_path   TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    indexed_at  REAL NOT NULL,    -- Unix timestamp
    chunk_count INTEGER NOT NULL DEFAULT 0,
    file_size   INTEGER NOT NULL DEFAULT 0
);
"""

CREATE_META_TABLE = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ── MetadataStore ─────────────────────────────────────────────────────────────

class MetadataStore:
    """
    Lightweight SQLite store for tracking indexed files.
    Thread-safe: each call opens/closes or uses check_same_thread=False.
    """

    def __init__(self, db_path: Path = METADATA_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(CREATE_FILES_TABLE)
            conn.execute(CREATE_META_TABLE)
            conn.commit()

    # ── File registry ─────────────────────────────────────────────────────────

    def get_file_hash(self, file_path: str) -> Optional[str]:
        """Return stored hash for a file path, or None if not indexed."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content_hash FROM indexed_files WHERE file_path = ?",
                (file_path,),
            ).fetchone()
        return row["content_hash"] if row else None

    def upsert_file(
        self,
        file_path: str,
        content_hash: str,
        indexed_at: float,
        chunk_count: int,
        file_size: int,
    ) -> None:
        """Insert or update a file record."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO indexed_files
                    (file_path, content_hash, indexed_at, chunk_count, file_size)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(file_path) DO UPDATE SET
                    content_hash = excluded.content_hash,
                    indexed_at   = excluded.indexed_at,
                    chunk_count  = excluded.chunk_count,
                    file_size    = excluded.file_size
                """,
                (file_path, content_hash, indexed_at, chunk_count, file_size),
            )
            conn.commit()

    def delete_file(self, file_path: str) -> None:
        """Remove a file record (called when a file is deleted from disk)."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM indexed_files WHERE file_path = ?", (file_path,)
            )
            conn.commit()

    def get_all_files(self) -> list[dict]:
        """Return all indexed file records."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM indexed_files ORDER BY indexed_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_stats(self) -> dict:
        """Return aggregate statistics for the `synapse status` command."""
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*)        AS file_count,
                    SUM(chunk_count) AS total_chunks,
                    SUM(file_size)  AS total_bytes,
                    MAX(indexed_at) AS last_indexed
                FROM indexed_files
                """
            ).fetchone()
        return dict(row) if row else {}

    # ── Meta key-value ────────────────────────────────────────────────────────

    def set_meta(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            conn.commit()

    def get_meta(self, key: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    # ── Wipe ─────────────────────────────────────────────────────────────────

    def wipe(self) -> None:
        """Delete all records (called by `synapse wipe`)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM indexed_files")
            conn.execute("DELETE FROM meta")
            conn.commit()


# ── Utility ───────────────────────────────────────────────────────────────────

def hash_file(path: Path) -> str:
    """Return SHA-256 hex digest of a file's contents."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_needs_reindex(store: MetadataStore, path: Path) -> bool:
    """Return True if the file is new or its content has changed."""
    stored_hash = store.get_file_hash(str(path))
    if stored_hash is None:
        return True
    try:
        current_hash = hash_file(path)
    except OSError:
        return False
    return current_hash != stored_hash
