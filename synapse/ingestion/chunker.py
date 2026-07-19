"""
Text chunker: split file content into overlapping chunks for embedding.

Strategy:
- Code files: split at logical boundaries (blank lines, function/class defs)
  then further split oversized sections at token limit.
- Prose files (markdown, text): split at paragraph boundaries.
- Fallback: sliding window over tokens.

Token estimation: 1 token ≈ 4 characters (English/code approximation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ── Config ────────────────────────────────────────────────────────────────────

DEFAULT_CHUNK_SIZE = 512    # approximate tokens
DEFAULT_CHUNK_OVERLAP = 64  # tokens of overlap between consecutive chunks

CHARS_PER_TOKEN = 4  # rough approximation


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    content: str
    index: int      # position within the source file (0-based)


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_text(
    text: str,
    language: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """
    Split text into overlapping chunks.
    Returns a list of Chunk objects with content and index.
    """
    if not text.strip():
        return []

    if language in ("markdown", "mdx", "rst", "text"):
        segments = _split_prose(text)
    elif language in ("python", "typescript", "javascript", "go", "rust",
                      "java", "kotlin", "ruby", "php", "csharp", "swift",
                      "cpp", "c", "scala"):
        segments = _split_code(text, language)
    else:
        # Generic: split on blank lines, then merge
        segments = [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]

    return _merge_into_chunks(segments, chunk_size, chunk_overlap)


# ── Splitting strategies ──────────────────────────────────────────────────────

def _split_prose(text: str) -> list[str]:
    """Split markdown/prose on double newlines (paragraph boundaries)."""
    paragraphs = re.split(r"\n\s*\n", text)
    return [p.strip() for p in paragraphs if p.strip()]


def _split_code(text: str, language: str) -> list[str]:
    """
    Split code at top-level function/class boundaries.
    Falls back to blank-line splitting for unsupported languages.
    """
    # Patterns that signal a new logical block
    block_patterns = {
        "python": re.compile(r"^(def |class |async def )", re.MULTILINE),
        "typescript": re.compile(
            r"^(export |function |class |const |interface |type |enum )", re.MULTILINE
        ),
        "javascript": re.compile(
            r"^(export |function |class |const |let |var )", re.MULTILINE
        ),
        "go": re.compile(r"^func ", re.MULTILINE),
        "rust": re.compile(r"^(fn |pub fn |impl |struct |enum |trait )", re.MULTILINE),
        "java": re.compile(
            r"^(public |private |protected |class |interface |enum )", re.MULTILINE
        ),
    }

    pattern = block_patterns.get(language)
    if pattern is None:
        return [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]

    # Find all match positions
    positions = [m.start() for m in pattern.finditer(text)]
    if not positions:
        return [s.strip() for s in re.split(r"\n\s*\n", text) if s.strip()]

    segments = []
    for i, pos in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(text)
        segment = text[pos:end].strip()
        if segment:
            segments.append(segment)

    # Prepend anything before the first match (imports, module-level code)
    if positions[0] > 0:
        header = text[: positions[0]].strip()
        if header:
            segments.insert(0, header)

    return segments


# ── Merge into fixed-size chunks ──────────────────────────────────────────────

def _merge_into_chunks(
    segments: list[str],
    chunk_size: int,
    chunk_overlap: int,
) -> list[Chunk]:
    """
    Greedily merge segments into chunks of approximately chunk_size tokens.
    When a chunk is full, start a new one with chunk_overlap tokens of the
    previous chunk prepended (so context is preserved at boundaries).
    """
    max_chars = chunk_size * CHARS_PER_TOKEN
    overlap_chars = chunk_overlap * CHARS_PER_TOKEN

    chunks: list[Chunk] = []
    current_parts: list[str] = []
    current_len = 0
    chunk_index = 0

    def flush():
        nonlocal chunk_index, current_parts, current_len
        content = "\n\n".join(current_parts).strip()
        if content:
            chunks.append(Chunk(content=content, index=chunk_index))
            chunk_index += 1
        # Keep tail for overlap
        tail = content[-overlap_chars:] if overlap_chars < len(content) else content
        current_parts = [tail] if tail else []
        current_len = len(tail)

    for segment in segments:
        # If a single segment is itself too big, split it by lines
        if len(segment) > max_chars:
            sub_segments = _split_large_segment(segment, max_chars)
        else:
            sub_segments = [segment]

        for sub in sub_segments:
            if current_len + len(sub) + 2 > max_chars and current_parts:
                flush()
            current_parts.append(sub)
            current_len += len(sub) + 2  # +2 for "\n\n"

    # Flush whatever's left
    if current_parts:
        content = "\n\n".join(current_parts).strip()
        if content:
            chunks.append(Chunk(content=content, index=chunk_index))

    return chunks


def _split_large_segment(segment: str, max_chars: int) -> list[str]:
    """Split an oversized segment by lines into max_chars sub-segments."""
    lines = segment.splitlines(keepends=True)
    result = []
    current = []
    current_len = 0
    for line in lines:
        if current_len + len(line) > max_chars and current:
            result.append("".join(current).strip())
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        result.append("".join(current).strip())
    return [r for r in result if r]
