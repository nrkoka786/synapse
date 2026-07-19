"""
Synapse configuration management.
Config lives at ~/.synapse/config.toml on all platforms.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import tomli_w

# Python 3.11+ has tomllib built-in; older versions need tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomllib  # type: ignore[no-redef]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "Python < 3.11 requires 'tomli': pip install tomli"
            )

# ── Directory layout ──────────────────────────────────────────────────────────

SYNAPSE_DIR = Path.home() / ".synapse"
CONFIG_PATH = SYNAPSE_DIR / "config.toml"
DB_DIR = SYNAPSE_DIR / "db"
METADATA_PATH = SYNAPSE_DIR / "metadata.db"


# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG: dict[str, Any] = {
    "synapse": {
        "watch_paths": [],
        "ignore_patterns": [
            "*.pyc",
            "__pycache__",
            "node_modules",
            ".git",
            "dist",
            "build",
            ".venv",
            "venv",
            "*.egg-info",
            ".pytest_cache",
            "*.min.js",
            "*.min.css",
            "*.lock",
            "package-lock.json",
        ],
    },
    "embedding": {
        "provider": "local",
        "model": "nomic-ai/nomic-embed-text-v1.5",
        "chunk_size": 512,
        "chunk_overlap": 64,
    },
}


# ── Public helpers ────────────────────────────────────────────────────────────

def ensure_synapse_dir() -> None:
    """Create ~/.synapse and subdirectories if they don't exist."""
    SYNAPSE_DIR.mkdir(parents=True, exist_ok=True)
    DB_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> dict[str, Any]:
    """
    Load config from ~/.synapse/config.toml.
    Returns DEFAULT_CONFIG merged with whatever the user has set.
    Missing keys fall back to defaults.
    """
    ensure_synapse_dir()

    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG.copy()

    with open(CONFIG_PATH, "rb") as f:
        user_config = tomllib.load(f)

    # Deep merge: user values override defaults
    merged = _deep_merge(DEFAULT_CONFIG, user_config)
    return merged


def save_config(config: dict[str, Any]) -> None:
    """Write config dict to ~/.synapse/config.toml."""
    ensure_synapse_dir()
    with open(CONFIG_PATH, "wb") as f:
        tomli_w.dump(config, f)


def add_watch_path(path: str) -> None:
    """Add a folder to the watch_paths list (idempotent)."""
    config = load_config()
    watch_paths: list[str] = config["synapse"]["watch_paths"]
    normalized = str(Path(path).resolve())
    if normalized not in watch_paths:
        watch_paths.append(normalized)
    config["synapse"]["watch_paths"] = watch_paths
    save_config(config)


def get_watch_paths() -> list[Path]:
    """Return list of Path objects for all configured watch paths."""
    config = load_config()
    return [Path(p) for p in config["synapse"]["watch_paths"]]


def get_ignore_patterns() -> list[str]:
    """Return glob patterns for files/folders to skip."""
    config = load_config()
    return config["synapse"].get("ignore_patterns", [])


def get_embedding_config() -> dict[str, Any]:
    """Return the [embedding] section of the config."""
    return load_config()["embedding"]


def claude_desktop_config_path() -> Path:
    """
    Return the Claude Desktop config file path for the current OS.
    Windows: %APPDATA%\\Claude\\claude_desktop_config.json
    macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
    Linux:   ~/.config/claude/claude_desktop_config.json
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:
        return Path.home() / ".config" / "claude" / "claude_desktop_config.json"


# ── Internal helpers ──────────────────────────────────────────────────────────

def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base (override wins on conflicts)."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
