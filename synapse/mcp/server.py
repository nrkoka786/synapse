"""
Synapse MCP server.
Exposes two tools to Claude Desktop (and any MCP client):

  recall(query, limit?)  — semantic search over your indexed codebase
  context(path)          — retrieve the full indexed content of a file

Run as:
  python -m synapse.mcp.server      (for development)
  synapse-mcp                       (after pip install)

Claude Desktop config (Windows):
  %APPDATA%\\Claude\\claude_desktop_config.json
  Add to "mcpServers":
  {
    "synapse": {
      "command": "synapse-mcp",
      "args": []
    }
  }
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    from fastmcp import FastMCP
except ImportError:
    raise ImportError(
        "fastmcp is required: pip install fastmcp\n"
        "Or install everything: pip install synapse-mcp"
    )

from synapse.store.metadata import MetadataStore
from synapse.store.vectordb import VectorDB
from synapse.daemon import search as daemon_search, get_file_context

logger = logging.getLogger(__name__)

# ── FastMCP app ───────────────────────────────────────────────────────────────

mcp = FastMCP(
    "Synapse",
    instructions=(
        "Synapse gives you access to the user's locally-indexed codebase. "
        "Use `recall` to find relevant code, patterns, or documentation by semantic query. "
        "Use `context` to retrieve the full content of a specific file. "
        "Always prefer calling these tools before asking the user to share code — "
        "the answer is likely already in the index."
    ),
)

# Shared store instances (initialized lazily at first tool call)
_metadata: MetadataStore | None = None
_vectordb: VectorDB | None = None


def _get_stores() -> tuple[MetadataStore, VectorDB]:
    global _metadata, _vectordb
    if _metadata is None:
        _metadata = MetadataStore()
    if _vectordb is None:
        _vectordb = VectorDB()
    return _metadata, _vectordb


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def recall(query: str, limit: int = 8) -> str:
    """
    Search the user's indexed codebase using semantic similarity.

    Use this to find:
    - Functions, classes, or modules related to a topic
    - How a pattern or convention is used across the project
    - Relevant context before suggesting code changes
    - Prior implementations of similar features

    Args:
        query: Natural language description of what you're looking for.
               Examples: "error handling in the API client",
                         "database connection setup", "auth middleware"
        limit: Number of results to return (default 8, max 20).

    Returns:
        Formatted list of relevant code snippets with file paths.
    """
    _, vectordb = _get_stores()
    limit = max(1, min(limit, 20))

    try:
        results = daemon_search(query, vectordb, limit=limit)
    except Exception as exc:
        logger.error(f"Search error: {exc}")
        return f"Search failed: {exc}\nMake sure Synapse has indexed your project (`synapse start`)."

    if not results:
        return (
            "No results found. The index may be empty.\n"
            "Run `synapse index <path>` to index your project first."
        )

    lines = [f"Found {len(results)} relevant snippets for: '{query}'\n"]
    for i, result in enumerate(results, 1):
        file_path = result.get("file_path", "unknown")
        content = result.get("content", "")
        language = result.get("language", "")
        chunk_index = result.get("chunk_index", 0)
        score = result.get("_distance", None)

        # Make path relative-looking for readability
        try:
            display_path = str(Path(file_path).name)
            full_path = file_path
        except Exception:
            display_path = file_path
            full_path = file_path

        score_str = f" (relevance: {1 - score:.2f})" if score is not None else ""
        lines.append(f"{'─' * 60}")
        lines.append(f"[{i}] {display_path}{score_str}")
        lines.append(f"    Full path: {full_path}")
        lines.append(f"    Language: {language} | Chunk #{chunk_index}")
        lines.append("")
        # Trim very long chunks for readability in Claude context window
        content_display = content if len(content) <= 1500 else content[:1500] + "\n... [truncated]"
        lines.append(content_display)
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def context(path: str) -> str:
    """
    Retrieve the full indexed content of a specific file.

    Use this when you know exactly which file you need, for example:
    - Before modifying a specific module
    - To understand the full implementation of a function
    - To check imports, dependencies, or exports

    Args:
        path: Absolute or partial file path. Partial paths are matched
              against the file_path stored in the index.
              Examples: "C:/Users/me/project/src/api/client.ts"
                        "client.ts"   (matched by filename)

    Returns:
        The full indexed text of the file, or a not-found message.
    """
    _, vectordb = _get_stores()

    # Try exact path first
    content = get_file_context(path, vectordb)
    if content:
        return f"File: {path}\n\n{content}"

    # Try matching by filename
    try:
        filename = Path(path).name
        all_files = _metadata.get_all_files() if _metadata else []
        matches = [
            f["file_path"]
            for f in all_files
            if Path(f["file_path"]).name == filename
        ]
        if matches:
            matched_path = matches[0]
            content = get_file_context(matched_path, vectordb)
            if content:
                return f"File: {matched_path}\n\n{content}"
    except Exception:
        pass

    return (
        f"File not found in Synapse index: {path}\n\n"
        "Options:\n"
        "  • Run `synapse status` to see what's indexed\n"
        "  • Run `synapse index <folder>` to add more folders\n"
        "  • Use the `recall` tool to search by description instead"
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    """Entry point for the `synapse-mcp` command."""
    logging.basicConfig(level=logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    run()
