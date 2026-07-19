"""
Synapse daemon: the main coordinator.
Orchestrates ingestion, embedding, and storage.
Used both for the initial bulk index and incremental updates from the watcher.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

from synapse.config import get_embedding_config, get_ignore_patterns, get_watch_paths
from synapse.ingestion.chunker import chunk_text
from synapse.ingestion.reader import read_file, should_ignore
from synapse.store.metadata import MetadataStore, file_needs_reindex, hash_file
from synapse.store.vectordb import VectorDB, make_chunk_record

logger = logging.getLogger(__name__)


# ── Embedder resolver ─────────────────────────────────────────────────────────

def _get_encoder():
    """Return (encode_batch, encode_query) functions based on config."""
    cfg = get_embedding_config()
    provider = cfg.get("provider", "local")
    if provider == "openai":
        from synapse.embedding.openai_emb import encode, encode_query
    else:
        from synapse.embedding.local import encode, encode_query
    return encode, encode_query


# ── Core indexing logic ───────────────────────────────────────────────────────

def index_file(
    path: Path,
    metadata: MetadataStore,
    vectordb: VectorDB,
    encode_batch,
    force: bool = False,
) -> Optional[int]:
    """
    Index a single file.

    Returns the number of chunks written, or None if the file was skipped.
    Skips files that haven't changed since last index (unless force=True).
    """
    path = path.resolve()

    if not path.exists() or not path.is_file():
        return None

    ignore_patterns = get_ignore_patterns()
    if should_ignore(path, ignore_patterns):
        return None

    if not force and not file_needs_reindex(metadata, path):
        return None

    result = read_file(path)
    if result is None:
        return None

    text, language = result
    cfg = get_embedding_config()
    chunks = chunk_text(
        text,
        language=language,
        chunk_size=cfg.get("chunk_size", 512),
        chunk_overlap=cfg.get("chunk_overlap", 64),
    )

    if not chunks:
        return None

    # Embed all chunks in one batch call
    try:
        embeddings = encode_batch([c.content for c in chunks])
    except Exception as exc:
        logger.error(f"Embedding error for {path}: {exc}")
        return None

    # Remove stale chunks for this file, then insert fresh ones
    file_path_str = str(path)
    vectordb.delete_file(file_path_str)

    records = [
        make_chunk_record(
            file_path=file_path_str,
            content=chunk.content,
            vector=embeddings[i],
            language=language,
            chunk_index=chunk.index,
        )
        for i, chunk in enumerate(chunks)
    ]
    vectordb.upsert_chunks(records)

    # Update metadata
    content_hash = hash_file(path)
    metadata.upsert_file(
        file_path=file_path_str,
        content_hash=content_hash,
        indexed_at=time.time(),
        chunk_count=len(chunks),
        file_size=path.stat().st_size,
    )

    return len(chunks)


def remove_file(
    path: Path,
    metadata: MetadataStore,
    vectordb: VectorDB,
) -> None:
    """Remove a deleted file from both stores."""
    file_path_str = str(path.resolve())
    vectordb.delete_file(file_path_str)
    metadata.delete_file(file_path_str)
    logger.debug(f"Removed: {path}")


# ── Bulk index ────────────────────────────────────────────────────────────────

def index_paths(
    paths: list[Path],
    metadata: MetadataStore,
    vectordb: VectorDB,
    force: bool = False,
    progress_callback=None,
) -> dict:
    """
    Walk a list of directories (or individual files) and index everything.

    Args:
        paths: Directories or files to index.
        metadata: MetadataStore instance.
        vectordb: VectorDB instance.
        force: If True, re-index even unchanged files.
        progress_callback: Optional callable(file_path, status) for UI updates.

    Returns:
        dict with keys: indexed, skipped, errors, total_chunks
    """
    encode_batch, _ = _get_encoder()
    ignore_patterns = get_ignore_patterns()

    stats = {"indexed": 0, "skipped": 0, "errors": 0, "total_chunks": 0}

    all_files: list[Path] = []
    for p in paths:
        p = Path(p).resolve()
        if p.is_file():
            all_files.append(p)
        elif p.is_dir():
            all_files.extend(
                f for f in p.rglob("*")
                if f.is_file() and not should_ignore(f, ignore_patterns)
            )

    for file_path in all_files:
        try:
            chunk_count = index_file(file_path, metadata, vectordb, encode_batch, force=force)
            if chunk_count is None:
                stats["skipped"] += 1
                status = "skipped"
            else:
                stats["indexed"] += 1
                stats["total_chunks"] += chunk_count
                status = "indexed"
        except Exception as exc:
            stats["errors"] += 1
            status = "error"
            logger.error(f"Error indexing {file_path}: {exc}")

        if progress_callback:
            progress_callback(file_path, status)

    # Rebuild ANN index if warranted
    vectordb.rebuild_index()

    return stats


# ── Watch callback ────────────────────────────────────────────────────────────

def make_watch_callback(metadata: MetadataStore, vectordb: VectorDB):
    """
    Returns a function suitable for passing to FileWatcher.
    Handles file created/modified/deleted events.
    """
    encode_batch, _ = _get_encoder()

    def callback(path: Path, event_type: str) -> None:
        if event_type in ("created", "modified"):
            chunk_count = index_file(path, metadata, vectordb, encode_batch, force=True)
            if chunk_count is not None:
                logger.info(f"Re-indexed {path.name} → {chunk_count} chunks")
        elif event_type == "deleted":
            remove_file(path, metadata, vectordb)
            logger.info(f"Removed {path.name} from index")

    return callback


# ── Search ────────────────────────────────────────────────────────────────────

def search(
    query: str,
    vectordb: VectorDB,
    limit: int = 8,
) -> list[dict]:
    """
    Semantic search over the indexed codebase.
    Returns list of result dicts sorted by relevance.
    """
    _, encode_query = _get_encoder()
    query_vector = encode_query(query)
    return vectordb.search(query_vector, limit=limit)


def get_file_context(
    path_str: str,
    vectordb: VectorDB,
) -> Optional[str]:
    """
    Return the full indexed text of a specific file, in chunk order.
    Returns None if the file is not in the index.
    """
    path = Path(path_str).resolve()
    chunks = vectordb.get_by_file(str(path))
    if not chunks:
        return None
    return "\n\n".join(c["content"] for c in chunks)
