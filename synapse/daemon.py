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


# ── Supported embedding providers ────────────────────────────────────────────
#
#   provider      package             key required        notes
#   ──────────    ─────────────────   ─────────────────   ──────────────────────
#   local         sentence-tfmrs      none                default, ~400MB DL
#   openai        openai              OPENAI_API_KEY      text-embedding-3-small
#   ollama        (built-in urllib)   none                needs Ollama running
#   gemini        google-genai        GEMINI_API_KEY      text-embedding-004
#   cohere        cohere              COHERE_API_KEY      embed-english-v3.0
#
# Set [embedding] provider = "<name>" in ~/.synapse/config.toml


_PROVIDERS = {
    "local": "synapse.embedding.local",
    "openai": "synapse.embedding.openai_emb",
    "ollama": "synapse.embedding.ollama",
    "gemini": "synapse.embedding.gemini",
    "cohere": "synapse.embedding.cohere",
}


def _get_encoder():
    """
    Return (encode_batch, encode_query) functions for the configured provider.

    encode_batch(texts: list[str]) -> list[list[float]]
    encode_query(query: str)       -> list[float]
    """
    cfg = get_embedding_config()
    provider = cfg.get("provider", "local").lower().strip()

    module_path = _PROVIDERS.get(provider)
    if module_path is None:
        supported = ", ".join(f'"{p}"' for p in _PROVIDERS)
        raise ValueError(
            f"Unknown embedding provider: '{provider}'.\n"
            f"Supported providers: {supported}\n"
            f"Set [embedding] provider in ~/.synapse/config.toml"
        )

    import importlib
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        _provider_install_hint(provider, exc)

    return module.encode, module.encode_query


def _provider_install_hint(provider: str, exc: ImportError) -> None:
    """Raise a user-friendly error with the install command for a provider."""
    hints = {
        "openai": "pip install synapse-mcp[openai]  or  pip install openai",
        "ollama": "No extra install needed — start Ollama: https://ollama.com/download",
        "gemini": "pip install synapse-mcp[gemini]  or  pip install google-genai",
        "cohere": "pip install synapse-mcp[cohere]  or  pip install cohere",
    }
    hint = hints.get(provider, f"pip install synapse-mcp[{provider}]")
    raise ImportError(
        f"Embedding provider '{provider}' requires an additional package.\n"
        f"Install with: {hint}\n"
        f"Original error: {exc}"
    ) from exc


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

    try:
        embeddings = encode_batch([c.content for c in chunks])
    except Exception as exc:
        logger.error(f"Embedding error for {path}: {exc}")
        return None

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
