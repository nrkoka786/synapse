"""
Ollama embedding provider.

Runs entirely on your machine via the Ollama server (https://ollama.com).
No API key. No data leaves your machine.

Recommended model: nomic-embed-text (768-dim, matches Synapse default schema)
Other options: mxbai-embed-large (1024-dim, set embedding.dim = 1024 in config)

Setup:
    1. Install Ollama: https://ollama.com/download
    2. Pull the model: ollama pull nomic-embed-text
    3. Ollama runs automatically in the background.

Config (~/.synapse/config.toml):
    [embedding]
    provider = "ollama"
    model = "nomic-embed-text"
    ollama_url = "http://localhost:11434"   # default
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Union

EMBEDDING_DIM = 768
_DEFAULT_MODEL = "nomic-embed-text"
_DEFAULT_URL = "http://localhost:11434"


def _get_config() -> tuple[str, str]:
    """Return (model_name, base_url) from config or env vars."""
    from synapse.config import get_embedding_config
    cfg = get_embedding_config()
    model = cfg.get("model", _DEFAULT_MODEL)
    url = cfg.get("ollama_url", os.environ.get("OLLAMA_HOST", _DEFAULT_URL))
    return model, url.rstrip("/")


def _embed(texts: list[str]) -> list[list[float]]:
    """Call the Ollama /api/embed endpoint (batch supported in Ollama v0.3+)."""
    model, base_url = _get_config()
    endpoint = f"{base_url}/api/embed"

    payload = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot reach Ollama at {base_url}.\n"
            "Make sure Ollama is running: https://ollama.com/download\n"
            f"Original error: {exc}"
        ) from exc

    embeddings = data.get("embeddings") or data.get("embedding")
    if embeddings is None:
        raise ValueError(f"Unexpected Ollama response shape: {list(data.keys())}")

    # Single input may return a flat vector rather than list-of-lists
    if embeddings and isinstance(embeddings[0], float):
        embeddings = [embeddings]

    return [list(map(float, emb)) for emb in embeddings]


def encode(text: Union[str, list[str]]) -> list[list[float]]:
    """
    Encode one or more texts into embedding vectors via Ollama.

    Args:
        text: A single string or list of strings.

    Returns:
        List of float lists, one per input text.
    """
    texts = [text] if isinstance(text, str) else text
    return _embed(texts)


def encode_query(query: str) -> list[float]:
    """Encode a search query. Returns a single embedding vector."""
    return _embed([query])[0]


def embedding_dim() -> int:
    return EMBEDDING_DIM


def check_model_available() -> bool:
    """
    Verify the configured model is pulled locally in Ollama.
    Raises with a helpful install message if not.
    """
    model, base_url = _get_config()
    try:
        req = urllib.request.Request(f"{base_url}/api/tags")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        pulled = [m["name"].split(":")[0] for m in data.get("models", [])]
        if model.split(":")[0] not in pulled:
            raise RuntimeError(
                f"Model '{model}' is not pulled in Ollama.\n"
                f"Run: ollama pull {model}\n"
                f"Available models: {', '.join(pulled) or 'none yet'}"
            )
        return True
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Ollama is not running at {base_url}.\n"
            "Start it: ollama serve\n"
            "Install from: https://ollama.com/download"
        ) from exc
