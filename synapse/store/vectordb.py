"""
LanceDB vector store for Synapse chunks.
All data stays on disk under ~/.synapse/db/.
No server required — LanceDB is embedded.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import pyarrow as pa

from synapse.config import DB_DIR

try:
    import lancedb
except ImportError:
    raise ImportError("lancedb is required: pip install lancedb")


# ── Schema ────────────────────────────────────────────────────────────────────

EMBEDDING_DIM = 768  # nomic-embed-text-v1.5 output dimension

CHUNK_SCHEMA = pa.schema(
    [
        pa.field("chunk_id", pa.string()),       # "{file_path}::{chunk_index}"
        pa.field("file_path", pa.string()),       # absolute path to source file
        pa.field("content", pa.string()),         # raw text of the chunk
        pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM)),
        pa.field("language", pa.string()),        # inferred from extension
        pa.field("chunk_index", pa.int32()),      # position within file
        pa.field("indexed_at", pa.float64()),     # Unix timestamp
    ]
)

TABLE_NAME = "chunks"


# ── VectorDB ─────────────────────────────────────────────────────────────────

class VectorDB:
    """
    Thin wrapper around LanceDB.
    Supports upsert, search, delete-by-file, and wipe.
    """

    def __init__(self, db_dir: Path = DB_DIR):
        self.db_dir = db_dir
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(self.db_dir))
        self._table = self._get_or_create_table()

    def _get_or_create_table(self):
        try:
            return self._db.open_table(TABLE_NAME)
        except Exception:
            # Table doesn't exist yet — create with schema
            return self._db.create_table(TABLE_NAME, schema=CHUNK_SCHEMA)

    # ── Write ─────────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: list[dict]) -> None:
        """
        Insert or replace chunks for a given file.
        Each chunk dict must have keys matching CHUNK_SCHEMA.
        Caller is responsible for first calling delete_file() to remove stale chunks.
        """
        if not chunks:
            return
        self._table.add(chunks)

    def delete_file(self, file_path: str) -> None:
        """
        Remove all chunks belonging to a specific file.
        Call before re-indexing a changed file.
        """
        try:
            self._table.delete(f"file_path = '{_escape(file_path)}'")
        except Exception:
            pass  # Table may be empty; safe to ignore

    # ── Search ────────────────────────────────────────────────────────────────

    def search(
        self,
        query_vector: list[float],
        limit: int = 8,
        file_path_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Semantic nearest-neighbour search.
        Returns list of chunk dicts, best match first.
        """
        query = self._table.search(query_vector).limit(limit)

        if file_path_filter:
            query = query.where(f"file_path = '{_escape(file_path_filter)}'")

        results = query.to_list()
        return results

    def get_by_file(self, file_path: str) -> list[dict]:
        """Return all chunks for a specific file, ordered by chunk_index."""
        try:
            results = (
                self._table.search()
                .where(f"file_path = '{_escape(file_path)}'")
                .to_list()
            )
            return sorted(results, key=lambda r: r.get("chunk_index", 0))
        except Exception:
            return []

    def count(self) -> int:
        """Total number of chunks in the store."""
        try:
            return self._table.count_rows()
        except Exception:
            return 0

    # ── Admin ─────────────────────────────────────────────────────────────────

    def wipe(self) -> None:
        """Delete the entire table and recreate it empty."""
        try:
            self._db.drop_table(TABLE_NAME)
        except Exception:
            pass
        self._table = self._get_or_create_table()

    def rebuild_index(self) -> None:
        """
        Build/rebuild the ANN vector index for fast approximate search.
        Only useful once the table has 1000+ rows.
        """
        n = self.count()
        if n < 256:
            return  # LanceDB does brute-force below this threshold; no index needed
        try:
            self._table.create_index(
                metric="cosine",
                num_partitions=min(256, n // 40),
                num_sub_vectors=96,
            )
        except Exception:
            pass  # Index may already exist


# ── Helpers ───────────────────────────────────────────────────────────────────

def _escape(s: str) -> str:
    """Minimal SQL string escape for LanceDB filter strings."""
    return s.replace("'", "''").replace("\\", "\\\\")


def make_chunk_record(
    file_path: str,
    content: str,
    vector: list[float],
    language: str,
    chunk_index: int,
) -> dict:
    """Build a chunk dict ready for upsert_chunks()."""
    return {
        "chunk_id": f"{file_path}::{chunk_index}",
        "file_path": file_path,
        "content": content,
        "vector": vector,
        "language": language,
        "chunk_index": chunk_index,
        "indexed_at": time.time(),
    }
