"""
Cohere embedding provider.

Uses the Cohere embed-english-v3.0 model (1024-dim by default,
truncated to 768 to match Synapse's schema).

Cohere offers a generous free tier for personal use.

Setup:
    pip install synapse-mcp[cohere]
    export COHERE_API_KEY=your_key_here

    Get a free API key at: https://dashboard.cohere.com/api-keys

Config (~/.synapse/config.toml):
    [embedding]
    provider = "cohere"
    model = "embed-english-v3.0"   # default; use "embed-multilingual-v3.0"
                                   # for non-English codebases
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

EMBEDDING_DIM = 768
_DEFAULT_MODEL = "embed-english-v3.0"
_INPUT_TYPE_DOC = "search_document"
_INPUT_TYPE_QUERY = "search_query"


@lru_cache(maxsize=1)
def _get_client():
    try:
        import cohere
    except ImportError:
        raise ImportError(
            "cohere package is required for Cohere embeddings.\n"
            "Install with: pip install synapse-mcp[cohere]\n"
            "Or manually: pip install cohere"
        )

    api_key = os.environ.get("COHERE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "COHERE_API_KEY environment variable is not set.\n"
            "Get a free key at: https://dashboard.cohere.com/api-keys\n"
            "Then: export COHERE_API_KEY=your_key"
        )
    return cohere.Client(api_key=api_key)


def _get_model() -> str:
    from synapse.config import get_embedding_config
    cfg = get_embedding_config()
    return cfg.get("model", _DEFAULT_MODEL)


def _truncate(vector: list[float]) -> list[float]:
    """Truncate to EMBEDDING_DIM and re-normalise to unit length."""
    import math
    v = vector[:EMBEDDING_DIM]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


def encode(text: Union[str, list[str]]) -> list[list[float]]:
    """
    Encode one or more texts via the Cohere Embed API.

    Uses search_document input type (optimised for retrieval).
    Vectors are truncated from 1024 to 768 dims and re-normalised.

    Args:
        text: A single string or list of strings.

    Returns:
        List of float lists (768-dim), one per input text.
    """
    client = _get_client()
    model = _get_model()
    texts = [text] if isinstance(text, str) else text

    response = client.embed(
        texts=texts,
        model=model,
        input_type=_INPUT_TYPE_DOC,
        embedding_types=["float"],
    )
    return [_truncate(emb) for emb in response.embeddings.float]


def encode_query(query: str) -> list[float]:
    """
    Encode a search query with search_query input type.
    Cohere distinguishes query vs document embeddings for better retrieval.
    Returns a single 768-dim embedding vector.
    """
    client = _get_client()
    model = _get_model()

    response = client.embed(
        texts=[query],
        model=model,
        input_type=_INPUT_TYPE_QUERY,
        embedding_types=["float"],
    )
    return _truncate(response.embeddings.float[0])


def embedding_dim() -> int:
    return EMBEDDING_DIM
