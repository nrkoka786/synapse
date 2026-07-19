"""
File reader: given a file path, return its text content and detected language.
Handles code files, markdown, plain text, and JSON/YAML config files.
Skips binary files gracefully.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# ── Language detection ────────────────────────────────────────────────────────

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    # Python
    ".py": "python",
    ".pyi": "python",
    # JavaScript / TypeScript
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".d.ts": "typescript",
    # Web
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".vue": "vue",
    ".svelte": "svelte",
    # Backend languages
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".swift": "swift",
    # Shell
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".ps1": "powershell",
    ".psm1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    # Data / Config
    ".json": "json",
    ".jsonc": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".ini": "ini",
    ".env": "dotenv",
    ".xml": "xml",
    ".csv": "csv",
    # Docs
    ".md": "markdown",
    ".mdx": "mdx",
    ".rst": "rst",
    ".txt": "text",
    # SQL
    ".sql": "sql",
    # Infra
    ".tf": "terraform",
    ".hcl": "hcl",
    ".dockerfile": "dockerfile",
    # Misc
    ".graphql": "graphql",
    ".gql": "graphql",
    ".proto": "protobuf",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
}

# Files to read even if they have no extension
EXTENSIONLESS_NAMES: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gemfile": "ruby",
    "rakefile": "ruby",
    "procfile": "text",
    "vagrantfile": "ruby",
    ".env": "dotenv",
    ".gitignore": "text",
    ".gitattributes": "text",
    ".editorconfig": "text",
    ".npmrc": "text",
    ".nvmrc": "text",
}

# Hard size limit: skip files larger than this (bytes)
MAX_FILE_SIZE = 512 * 1024  # 512 KB


# ── Public API ────────────────────────────────────────────────────────────────

def detect_language(path: Path) -> Optional[str]:
    """
    Return a language label for the given path, or None if unsupported.
    Checks extension first, then filename (case-insensitive).
    """
    suffix = path.suffix.lower()
    if suffix in EXTENSION_TO_LANGUAGE:
        return EXTENSION_TO_LANGUAGE[suffix]

    name_lower = path.name.lower()
    if name_lower in EXTENSIONLESS_NAMES:
        return EXTENSIONLESS_NAMES[name_lower]

    return None


def is_supported(path: Path) -> bool:
    """Return True if Synapse can read and index this file."""
    return detect_language(path) is not None


def read_file(path: Path) -> Optional[tuple[str, str]]:
    """
    Read a file and return (text_content, language).
    Returns None if the file is:
      - unsupported type
      - too large (>512 KB)
      - binary / undecodable
      - empty
    """
    language = detect_language(path)
    if language is None:
        return None

    try:
        size = path.stat().st_size
    except OSError:
        return None

    if size == 0:
        return None

    if size > MAX_FILE_SIZE:
        return None

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, PermissionError):
        return None

    text = text.strip()
    if not text:
        return None

    return text, language


def should_ignore(path: Path, ignore_patterns: list[str]) -> bool:
    """
    Return True if any part of the path matches an ignore pattern.
    Checks every component of the path (not just the filename).
    """
    from fnmatch import fnmatch

    path_str = str(path)
    for part in path.parts:
        for pattern in ignore_patterns:
            if fnmatch(part, pattern):
                return True
    # Also check full path string
    for pattern in ignore_patterns:
        if fnmatch(path_str, pattern):
            return True
    return False
