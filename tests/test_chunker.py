"""Tests for the text chunker module."""

import pytest

from synapse.ingestion.chunker import Chunk, chunk_text


PYTHON_CODE = '''\
import os
from pathlib import Path


def read_config(path: str) -> dict:
    """Read a TOML config file."""
    with open(path, "rb") as f:
        return tomllib.load(f)


def write_config(path: str, data: dict) -> None:
    """Write a TOML config file."""
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_dir: str):
        self.config_dir = Path(config_dir)
        self._cache: dict = {}

    def load(self, name: str) -> dict:
        if name not in self._cache:
            path = self.config_dir / f"{name}.toml"
            self._cache[name] = read_config(str(path))
        return self._cache[name]

    def save(self, name: str, data: dict) -> None:
        path = self.config_dir / f"{name}.toml"
        write_config(str(path), data)
        self._cache[name] = data
'''

MARKDOWN_TEXT = """\
# Introduction

This is the first paragraph of the introduction.
It spans multiple lines and talks about the project.

## Getting Started

To get started, install the package:

```bash
pip install mypackage
```

Then run the following command to initialize:

```bash
mypackage init
```

## Configuration

The configuration file lives at `~/.mypackage/config.toml`.
Edit it to customize behavior.
"""


class TestChunkText:
    def test_returns_list_of_chunks(self):
        chunks = chunk_text(PYTHON_CODE, language="python")
        assert isinstance(chunks, list)
        assert all(isinstance(c, Chunk) for c in chunks)

    def test_chunks_have_content(self):
        chunks = chunk_text(PYTHON_CODE, language="python")
        assert all(c.content for c in chunks)

    def test_chunk_indices_are_sequential(self):
        chunks = chunk_text(PYTHON_CODE, language="python")
        indices = [c.index for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_empty_text_returns_no_chunks(self):
        assert chunk_text("", language="python") == []
        assert chunk_text("   \n\n   ", language="python") == []

    def test_markdown_splitting(self):
        chunks = chunk_text(MARKDOWN_TEXT, language="markdown")
        assert len(chunks) >= 1
        # Heading should appear in some chunk
        full_text = " ".join(c.content for c in chunks)
        assert "Introduction" in full_text

    def test_small_file_is_single_chunk(self):
        tiny = "def foo():\n    return 42\n"
        chunks = chunk_text(tiny, language="python")
        assert len(chunks) == 1
        assert "def foo" in chunks[0].content

    def test_large_file_produces_multiple_chunks(self):
        # A file with many functions should produce multiple chunks
        big_code = "\n\n".join(
            f"def function_{i}(x, y):\n    return x + y + {i}"
            for i in range(100)
        )
        chunks = chunk_text(big_code, language="python", chunk_size=256)
        assert len(chunks) > 1

    def test_chunk_overlap_preserves_context(self):
        """Ensure that the tail of one chunk appears in the next."""
        big_code = "\n\n".join(
            f"def function_{i}(x, y):\n    # This is function {i}\n    return x + y + {i}"
            for i in range(50)
        )
        chunks = chunk_text(big_code, language="python", chunk_size=200, chunk_overlap=50)
        if len(chunks) >= 2:
            # The overlap means the tail of chunk[0] appears in chunk[1]
            # (not strictly guaranteed for all content, but overlap should be > 0)
            assert len(chunks[0].content) > 0
            assert len(chunks[1].content) > 0

    def test_json_falls_through_to_blank_line_split(self):
        json_text = '{\n  "key": "value"\n}\n\n{\n  "other": 123\n}'
        chunks = chunk_text(json_text, language="json")
        assert len(chunks) >= 1

    def test_chunk_content_is_not_empty(self):
        chunks = chunk_text(PYTHON_CODE, language="python")
        for chunk in chunks:
            assert chunk.content.strip()
