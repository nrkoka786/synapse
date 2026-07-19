"""
Local embedding using sentence-transformers.
Model: nomic-ai/nomic-embed-text-v1.5 (~400MB, cached after first download)
No API key required. Runs on CPU. Private by default.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Union

EMBEDDING_DIM = 768
_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"


@lru_cache(maxsize=1)
def _get_model():
    """
    Load the sentence-transformers model once and cache it.
    First call downloads ~400MB to ~/.cache/huggingface/hub/.
    Subsequent calls are instant (model is in memory).
    """
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        raise ImportError(
            "sentence-transformers is required for local embeddings.\n"
            "Install with: pip install sentence-transformers"
        )

    return SentenceTransformer(_MODEL_NAME, trust_remote_code=True)


def encode(text: Union[str, list[str]]) -> list[list[float]]:
    """
    Encode one or more texts into embedding vectors.

    Args:
        text: A single string or list of strings.

    Returns:
        List of float lists, one per input text.
        Each inner list has length EMBEDDING_DIM (768).
    """
    model = _get_model()
    single = isinstance(text, str)
    texts = [text] if single else text

    # nomic-embed requires a task prefix for retrieval use-cases
    prefixed = [f"search_document: {t}" for t in texts]

    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [emb.tolist() for emb in embeddings]


def encode_query(query: str) -> list[float]:
    """
    Encode a search query.
    Uses the 'search_query' prefix (distinct from document prefix).
    Returns a single embedding vector.
    """
    model = _get_model()
    prefixed = f"search_query: {query}"
    embedding = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


def embedding_dim() -> int:
    return EMBEDDING_DIM
