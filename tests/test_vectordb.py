"""Tests for the VectorDB store module."""

import tempfile
from pathlib import Path

import pytest

from synapse.store.vectordb import VectorDB, make_chunk_record, EMBEDDING_DIM


def _fake_vector(seed: int = 1) -> list[float]:
    """Generate a deterministic fake embedding vector for testing."""
    import math
    dim = EMBEDDING_DIM
    # Simple pattern: normalized sine values
    raw = [math.sin(seed * i * 0.01) for i in range(dim)]
    norm = math.sqrt(sum(x ** 2 for x in raw))
    return [x / norm for x in raw]


@pytest.fixture
def db(tmp_path):
    """Return a fresh VectorDB instance backed by a temp directory."""
    return VectorDB(db_dir=tmp_path / "testdb")


class TestVectorDB:
    def test_empty_db_count_is_zero(self, db):
        assert db.count() == 0

    def test_upsert_and_count(self, db):
        record = make_chunk_record(
            file_path="/project/main.py",
            content="def hello(): return 'world'",
            vector=_fake_vector(1),
            language="python",
            chunk_index=0,
        )
        db.upsert_chunks([record])
        assert db.count() == 1

    def test_upsert_multiple_chunks(self, db):
        records = [
            make_chunk_record(
                file_path="/project/main.py",
                content=f"chunk content {i}",
                vector=_fake_vector(i),
                language="python",
                chunk_index=i,
            )
            for i in range(5)
        ]
        db.upsert_chunks(records)
        assert db.count() == 5

    def test_delete_file_removes_its_chunks(self, db):
        records = [
            make_chunk_record(
                file_path="/project/main.py",
                content=f"chunk {i}",
                vector=_fake_vector(i),
                language="python",
                chunk_index=i,
            )
            for i in range(3)
        ]
        db.upsert_chunks(records)
        assert db.count() == 3

        db.delete_file("/project/main.py")
        assert db.count() == 0

    def test_delete_only_removes_target_file(self, db):
        for fp, seed in [("/a.py", 1), ("/b.py", 10)]:
            db.upsert_chunks([
                make_chunk_record(fp, "content", _fake_vector(seed), "python", 0)
            ])
        assert db.count() == 2

        db.delete_file("/a.py")
        assert db.count() == 1  # b.py remains

    def test_search_returns_results(self, db):
        records = [
            make_chunk_record(
                file_path=f"/project/file{i}.py",
                content=f"function implementation {i}",
                vector=_fake_vector(i),
                language="python",
                chunk_index=0,
            )
            for i in range(10)
        ]
        db.upsert_chunks(records)

        results = db.search(_fake_vector(0), limit=3)
        assert len(results) <= 3
        assert all("content" in r for r in results)

    def test_search_empty_db_returns_empty(self, db):
        results = db.search(_fake_vector(1), limit=5)
        assert results == []

    def test_get_by_file_returns_chunks_in_order(self, db):
        file_path = "/project/ordered.py"
        records = [
            make_chunk_record(file_path, f"chunk {i}", _fake_vector(i), "python", i)
            for i in range(3)
        ]
        db.upsert_chunks(records)

        chunks = db.get_by_file(file_path)
        assert [c["chunk_index"] for c in chunks] == [0, 1, 2]

    def test_get_by_file_unknown_returns_empty(self, db):
        assert db.get_by_file("/does/not/exist.py") == []

    def test_wipe_clears_all_data(self, db):
        db.upsert_chunks([
            make_chunk_record("/a.py", "content", _fake_vector(1), "python", 0)
        ])
        assert db.count() == 1

        db.wipe()
        assert db.count() == 0

    def test_make_chunk_record_structure(self):
        record = make_chunk_record(
            file_path="/project/test.py",
            content="test content",
            vector=_fake_vector(42),
            language="python",
            chunk_index=7,
        )
        assert record["chunk_id"] == "/project/test.py::7"
        assert record["file_path"] == "/project/test.py"
        assert record["content"] == "test content"
        assert record["language"] == "python"
        assert record["chunk_index"] == 7
        assert len(record["vector"]) == EMBEDDING_DIM
        assert isinstance(record["indexed_at"], float)
