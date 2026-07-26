"""
Synapse benchmark — measures retrieval quality over a set of preset queries.

Designed to be run after indexing to give developers confidence that Synapse
is finding the right code, and to produce a shareable score.

Usage:
    synapse benchmark
    synapse benchmark --queries my_queries.json
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Preset queries ─────────────────────────────────────────────────────────────
# Generic enough to apply to any codebase.
# A result is considered a "hit" if its relevance score >= MIN_RELEVANCE.

PRESET_QUERIES = [
    "error handling and exceptions",
    "configuration and settings",
    "authentication and authorization",
    "database connection and queries",
    "API client or HTTP requests",
    "logging and observability",
    "data models and schemas",
    "file reading and writing",
    "environment variables and secrets",
    "tests and test utilities",
]

MIN_RELEVANCE = 0.35   # 1 - cosine_distance threshold for a "hit"
RESULTS_PER_QUERY = 5  # how many results to retrieve per query


# ── Data types ─────────────────────────────────────────────────────────────────

@dataclass
class QueryResult:
    query: str
    hits: int              # results above MIN_RELEVANCE threshold
    total: int             # total results returned
    top_score: float       # best relevance score (0–1)
    avg_score: float       # average relevance across returned results
    latency_ms: float      # wall-clock time for this query
    top_file: str          # filename of best match


@dataclass
class BenchmarkReport:
    results: list[QueryResult] = field(default_factory=list)
    total_queries: int = 0
    queries_with_hits: int = 0
    avg_top_score: float = 0.0
    avg_latency_ms: float = 0.0
    overall_score: float = 0.0   # 0–100 composite score
    indexed_files: int = 0
    indexed_chunks: int = 0
    provider: str = "local"


# ── Core benchmark logic ───────────────────────────────────────────────────────

def run_benchmark(
    custom_queries: Optional[list[str]] = None,
    limit: int = RESULTS_PER_QUERY,
) -> BenchmarkReport:
    """
    Run all benchmark queries against the current index.

    Args:
        custom_queries: If provided, use these instead of PRESET_QUERIES.
        limit: Number of results to retrieve per query.

    Returns:
        BenchmarkReport with per-query and aggregate stats.
    """
    from synapse.store.vectordb import VectorDB
    from synapse.store.metadata import MetadataStore
    from synapse.daemon import search as daemon_search
    from synapse.config import get_embedding_config, load_config

    vectordb = VectorDB()
    metadata = MetadataStore()
    cfg = get_embedding_config()
    provider = cfg.get("provider", "local")
    stats = metadata.get_stats()

    queries = custom_queries or PRESET_QUERIES
    report = BenchmarkReport(
        total_queries=len(queries),
        indexed_files=stats.get("file_count", 0),
        indexed_chunks=stats.get("total_chunks", 0),
        provider=provider,
    )

    top_scores = []
    latencies = []

    for query in queries:
        t0 = time.perf_counter()
        try:
            raw = daemon_search(query, vectordb, limit=limit)
        except Exception:
            raw = []
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if not raw:
            report.results.append(QueryResult(
                query=query,
                hits=0,
                total=0,
                top_score=0.0,
                avg_score=0.0,
                latency_ms=elapsed_ms,
                top_file="(no results)",
            ))
            latencies.append(elapsed_ms)
            continue

        scores = [max(0.0, 1.0 - r.get("_distance", 1.0)) for r in raw]
        hits = sum(1 for s in scores if s >= MIN_RELEVANCE)
        top_score = max(scores)
        avg_score = sum(scores) / len(scores)
        top_file = Path(raw[0].get("file_path", "unknown")).name

        top_scores.append(top_score)
        latencies.append(elapsed_ms)

        if hits > 0:
            report.queries_with_hits += 1

        report.results.append(QueryResult(
            query=query,
            hits=hits,
            total=len(raw),
            top_score=top_score,
            avg_score=avg_score,
            latency_ms=elapsed_ms,
            top_file=top_file,
        ))

    report.avg_top_score = sum(top_scores) / len(top_scores) if top_scores else 0.0
    report.avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

    # Overall score: % of queries with at least one hit, weighted by avg relevance
    hit_rate = report.queries_with_hits / report.total_queries if report.total_queries else 0
    report.overall_score = round(hit_rate * report.avg_top_score * 100, 1)

    return report


def load_custom_queries(path: str) -> list[str]:
    """Load custom queries from a JSON file (list of strings)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Query file not found: {path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Query file must be a JSON array of strings.")
    return [str(q) for q in data if str(q).strip()]
