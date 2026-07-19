"""Tests for the file reader module."""

import tempfile
from pathlib import Path

import pytest

from synapse.ingestion.reader import (
    detect_language,
    is_supported,
    read_file,
    should_ignore,
)


class TestDetectLanguage:
    def test_python(self):
        assert detect_language(Path("main.py")) == "python"

    def test_typescript(self):
        assert detect_language(Path("app.ts")) == "typescript"
        assert detect_language(Path("component.tsx")) == "typescript"

    def test_javascript(self):
        assert detect_language(Path("index.js")) == "javascript"
        assert detect_language(Path("App.jsx")) == "javascript"

    def test_go(self):
        assert detect_language(Path("main.go")) == "go"

    def test_rust(self):
        assert detect_language(Path("lib.rs")) == "rust"

    def test_markdown(self):
        assert detect_language(Path("README.md")) == "markdown"

    def test_json(self):
        assert detect_language(Path("package.json")) == "json"

    def test_yaml(self):
        assert detect_language(Path("config.yaml")) == "yaml"
        assert detect_language(Path("docker-compose.yml")) == "yaml"

    def test_unsupported_extension(self):
        assert detect_language(Path("image.png")) is None
        assert detect_language(Path("archive.zip")) is None
        assert detect_language(Path("video.mp4")) is None

    def test_dockerfile_no_extension(self):
        assert detect_language(Path("Dockerfile")) == "dockerfile"
        assert detect_language(Path("dockerfile")) == "dockerfile"

    def test_case_insensitive_extension(self):
        assert detect_language(Path("Script.PY")) == "python"


class TestIsSupported:
    def test_supported_files(self):
        assert is_supported(Path("app.py"))
        assert is_supported(Path("index.ts"))
        assert is_supported(Path("README.md"))

    def test_unsupported_files(self):
        assert not is_supported(Path("photo.jpg"))
        assert not is_supported(Path("data.parquet"))
        assert not is_supported(Path("model.bin"))


class TestReadFile:
    def test_read_python_file(self, tmp_path):
        f = tmp_path / "hello.py"
        f.write_text("def greet():\n    return 'hello'\n", encoding="utf-8")
        result = read_file(f)
        assert result is not None
        text, language = result
        assert "def greet" in text
        assert language == "python"

    def test_skip_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("", encoding="utf-8")
        assert read_file(f) is None

    def test_skip_unsupported_extension(self, tmp_path):
        f = tmp_path / "image.png"
        f.write_bytes(b"\x89PNG\r\n")
        assert read_file(f) is None

    def test_skip_large_file(self, tmp_path):
        f = tmp_path / "huge.py"
        f.write_text("x = 1\n" * 200_000, encoding="utf-8")  # ~1.2MB
        assert read_file(f) is None

    def test_returns_stripped_text(self, tmp_path):
        f = tmp_path / "spaced.py"
        f.write_text("   \n\ndef foo(): pass\n\n   ", encoding="utf-8")
        result = read_file(f)
        assert result is not None
        text, _ = result
        assert not text.startswith(" ")
        assert not text.endswith(" ")


class TestShouldIgnore:
    def test_node_modules(self):
        path = Path("/project/node_modules/lodash/index.js")
        assert should_ignore(path, ["node_modules"])

    def test_pyc_files(self):
        path = Path("/project/app/__pycache__/main.cpython-311.pyc")
        assert should_ignore(path, ["*.pyc", "__pycache__"])

    def test_git_directory(self):
        path = Path("/project/.git/config")
        assert should_ignore(path, [".git"])

    def test_normal_file_not_ignored(self):
        path = Path("/project/src/main.py")
        assert not should_ignore(path, ["node_modules", ".git", "*.pyc"])

    def test_empty_patterns_ignores_nothing(self):
        path = Path("/project/anything.py")
        assert not should_ignore(path, [])
