"""
Synapse CLI — all commands a user will type.

  synapse init <path>        Add a folder and index it
  synapse start              Start MCP server + file watcher
  synapse status             Show index statistics
  synapse search <query>     Search the index from the terminal
  synapse explain <file>     Show what Synapse knows about a file
  synapse benchmark          Measure retrieval quality
  synapse wipe               Delete the entire local index
"""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

from synapse import __version__
from synapse.config import (
    add_watch_path,
    claude_desktop_config_path,
    get_ignore_patterns,
    get_watch_paths,
    load_config,
    SYNAPSE_DIR,
)
from synapse.store.metadata import MetadataStore
from synapse.store.vectordb import VectorDB

console = Console()


# ── Main group ────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(__version__, prog_name="synapse")
def main():
    """Synapse — Give any AI instant knowledge of your codebase.\n
    \b
    Quick start:
      synapse init C:/Projects/myapp
      claude mcp add synapse synapse-mcp
      (restart your AI tool)
      Done — it now knows your codebase.
    """
    pass


# ── init ─────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--force", is_flag=True, help="Re-index all files even if unchanged.")
def init(path: str, force: bool):
    """
    Add PATH to Synapse and index it immediately.

    After running this command, register Synapse with your AI tool:
      claude mcp add synapse synapse-mcp
    """
    folder = Path(path).resolve()
    console.print(f"\n[bold cyan]Synapse v{__version__}[/bold cyan]")
    console.print(f"Initializing: [green]{folder}[/green]\n")

    add_watch_path(str(folder))
    console.print("✓ Added to watch list")

    metadata = MetadataStore()
    vectordb = VectorDB()
    ignore_patterns = get_ignore_patterns()

    from synapse.ingestion.reader import is_supported, should_ignore

    all_files = [
        f for f in folder.rglob("*")
        if f.is_file()
        and not should_ignore(f, ignore_patterns)
        and is_supported(f)
    ]

    if not all_files:
        console.print("[yellow]No supported files found in this folder.[/yellow]")
        console.print("Supported types: .py .ts .js .go .rs .md .json .yaml and more.")
        return

    from synapse.daemon import index_file, _get_encoder
    from synapse.config import get_embedding_config

    cfg = get_embedding_config()
    provider = cfg.get("provider", "local")
    console.print(f"✓ Embedding provider: [bold]{provider}[/bold]")
    if provider == "local":
        console.print("  (First run downloads ~400MB model — please wait…)")

    encode_batch, _ = _get_encoder()

    indexed = skipped = errors = total_chunks = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(f"Indexing {len(all_files)} files…", total=len(all_files))

        for file_path in all_files:
            progress.update(task, description=f"[dim]{file_path.name}[/dim]")
            try:
                chunk_count = index_file(file_path, metadata, vectordb, encode_batch, force=force)
                if chunk_count is None:
                    skipped += 1
                else:
                    indexed += 1
                    total_chunks += chunk_count
            except Exception as exc:
                errors += 1
                logging.debug(f"Error indexing {file_path}: {exc}")
            progress.advance(task)

    console.print(f"\n✓ Indexed [bold green]{indexed}[/bold green] files · "
                  f"[bold]{total_chunks}[/bold] chunks · "
                  f"{skipped} skipped · {errors} errors")

    vectordb.rebuild_index()
    _print_mcp_instructions()


# ── start ─────────────────────────────────────────────────────────────────────

@main.command()
def start():
    """Start the Synapse MCP server and file watcher (manual mode)."""
    watch_paths = get_watch_paths()
    if not watch_paths:
        console.print("[red]No watch paths configured.[/red]")
        console.print("Run [bold]synapse init <path>[/bold] first.")
        sys.exit(1)

    console.print(f"\n[bold cyan]Synapse[/bold cyan] starting…")
    for p in watch_paths:
        console.print(f"  Watching: [green]{p}[/green]")

    metadata = MetadataStore()
    vectordb = VectorDB()

    from synapse.daemon import make_watch_callback
    from synapse.ingestion.watcher import FileWatcher

    callback = make_watch_callback(metadata, vectordb)
    watcher = FileWatcher(
        watch_paths=watch_paths,
        callback=callback,
        ignore_patterns=get_ignore_patterns(),
    )

    mcp_thread = threading.Thread(target=_run_mcp_server, daemon=True)
    watcher.start()
    mcp_thread.start()

    console.print("[bold green]✓ Running.[/bold green] Press Ctrl+C to stop.\n")

    def _shutdown(sig, frame):
        console.print("\nShutting down…")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    while True:
        time.sleep(1)


# ── status ────────────────────────────────────────────────────────────────────

@main.command()
def status():
    """Show what Synapse has indexed."""
    metadata = MetadataStore()
    vectordb = VectorDB()
    stats = metadata.get_stats()
    watch_paths = get_watch_paths()

    console.print(f"\n[bold cyan]Synapse v{__version__} — Status[/bold cyan]\n")

    if watch_paths:
        console.print("[bold]Watching:[/bold]")
        for p in watch_paths:
            exists = "✓" if Path(p).exists() else "[red]✗ (not found)[/red]"
            console.print(f"  {exists} {p}")
    else:
        console.print("[yellow]No watch paths configured. Run: synapse init <path>[/yellow]")

    file_count = stats.get("file_count") or 0
    total_chunks = stats.get("total_chunks") or 0
    total_bytes = stats.get("total_bytes") or 0
    last_indexed = stats.get("last_indexed")

    console.print(f"\n[bold]Index:[/bold]")
    console.print(f"  Files indexed:  [green]{file_count:,}[/green]")
    console.print(f"  Total chunks:   [green]{total_chunks:,}[/green]")
    console.print(f"  Data size:      {_human_bytes(total_bytes)}")
    console.print(f"  DB location:    {SYNAPSE_DIR / 'db'}")

    if last_indexed:
        import datetime
        dt = datetime.datetime.fromtimestamp(last_indexed)
        console.print(f"  Last indexed:   {dt.strftime('%Y-%m-%d %H:%M:%S')}")

    cfg = load_config()
    emb = cfg.get("embedding", {})
    console.print(f"\n[bold]Config:[/bold]")
    console.print(f"  Embedding:   {emb.get('provider', 'local')} / {emb.get('model', 'nomic-ai/nomic-embed-text-v1.5')}")
    console.print(f"  Chunk size:  {emb.get('chunk_size', 512)} tokens")
    console.print()


# ── search ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("query")
@click.option("--limit", "-n", default=5, show_default=True, help="Number of results.")
def search(query: str, limit: int):
    """Search your indexed codebase from the terminal.\n
    \b
    Examples:
      synapse search "error handling in API client"
      synapse search "database connection setup" -n 10
    """
    vectordb = VectorDB()
    from synapse.daemon import search as daemon_search

    console.print(f"\n[bold]Searching:[/bold] '{query}'\n")

    try:
        results = daemon_search(query, vectordb, limit=limit)
    except Exception as exc:
        console.print(f"[red]Search error: {exc}[/red]")
        console.print("Make sure you've run [bold]synapse init <path>[/bold] first.")
        sys.exit(1)

    if not results:
        console.print("[yellow]No results found. Is your project indexed?[/yellow]")
        console.print("Run [bold]synapse status[/bold] to check.")
        return

    for i, result in enumerate(results, 1):
        file_path = result.get("file_path", "unknown")
        content = result.get("content", "")
        language = result.get("language", "")
        score = result.get("_distance", None)
        score_str = f" [{1 - score:.2f}]" if score is not None else ""

        console.print(f"[bold cyan]{'─' * 70}[/bold cyan]")
        console.print(f"[bold]{i}. {Path(file_path).name}[/bold]{score_str} [dim]{file_path}[/dim]")
        console.print(f"[dim]Language: {language}[/dim]\n")
        preview = content[:500] + ("…" if len(content) > 500 else "")
        console.print(preview)
        console.print()


# ── explain ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("file_path")
@click.option("--related", "-r", default=5, show_default=True,
              help="Number of related files to show.")
def explain(file_path: str, related: int):
    """Show what Synapse knows about a file — its role, structure, and related files.\n
    \b
    Examples:
      synapse explain src/api/client.ts
      synapse explain payment.py
      synapse explain "C:/Projects/myapp/src/auth.ts"
    """
    import re
    from synapse.daemon import get_file_context, search as daemon_search
    from synapse.store.metadata import MetadataStore

    vectordb = VectorDB()
    metadata = MetadataStore()

    # ── Resolve the file in the index ─────────────────────────────────────────
    target = Path(file_path)
    all_files = metadata.get_all_files() if hasattr(metadata, "get_all_files") else []

    # Try exact match first, then filename match
    matched_path = None
    if target.is_absolute() and target.exists():
        matched_path = str(target.resolve())
    else:
        # Match by filename or partial path
        needle = target.name.lower()
        candidates = [
            f["file_path"] for f in all_files
            if Path(f["file_path"]).name.lower() == needle
               or str(f["file_path"]).replace("\\", "/").lower().endswith(
                   str(target).replace("\\", "/").lower()
               )
        ]
        if candidates:
            matched_path = candidates[0]

    console.print()

    if not matched_path:
        console.print(f"[red]File not found in Synapse index:[/red] {file_path}\n")
        console.print("Tips:")
        console.print("  • Run [bold]synapse status[/bold] to see what's indexed")
        console.print("  • Use just the filename: [bold]synapse explain client.ts[/bold]")
        console.print("  • Run [bold]synapse init <path>[/bold] to index a new folder")
        sys.exit(1)

    # ── Load chunks ───────────────────────────────────────────────────────────
    chunks = vectordb.get_by_file(matched_path)
    if not chunks:
        console.print(f"[yellow]No chunks found for {matched_path}[/yellow]")
        sys.exit(1)

    full_content = "\n\n".join(c["content"] for c in chunks)
    language = chunks[0].get("language", "unknown")
    file_meta = next((f for f in all_files if f["file_path"] == matched_path), {})
    file_size = file_meta.get("file_size", 0)
    chunk_count = len(chunks)

    # ── Extract structure (functions / classes) ───────────────────────────────
    structure = _extract_structure(full_content, language)

    # ── Find related files via semantic search ─────────────────────────────────
    fname = Path(matched_path).stem.replace("_", " ").replace("-", " ")
    search_query = f"{fname} {language}"
    try:
        raw_related = daemon_search(search_query, vectordb, limit=related + 1)
        related_files = []
        seen = set()
        for r in raw_related:
            rp = r.get("file_path", "")
            if rp == matched_path or rp in seen:
                continue
            seen.add(rp)
            score = max(0.0, 1.0 - r.get("_distance", 1.0))
            related_files.append((Path(rp).name, rp, score))
            if len(related_files) >= related:
                break
    except Exception:
        related_files = []

    # ── Render ────────────────────────────────────────────────────────────────
    display_name = Path(matched_path).name

    console.print(Panel(
        f"[bold white]{display_name}[/bold white]",
        title="[bold cyan]Synapse — File Explanation[/bold cyan]",
        border_style="cyan",
    ))

    # Metadata row
    console.print(f"\n[bold]File:[/bold]     {matched_path}")
    console.print(f"[bold]Language:[/bold] {language}")
    console.print(f"[bold]Size:[/bold]     {_human_bytes(file_size)}  ·  {chunk_count} chunk{'s' if chunk_count != 1 else ''} indexed")

    # Structure
    if structure:
        console.print(f"\n[bold]Structure[/bold] ({len(structure)} items):")
        for kind, name in structure[:20]:
            icon = "🔷" if kind == "class" else "🔹"
            console.print(f"  {icon} {kind:8s}  {name}")
        if len(structure) > 20:
            console.print(f"  [dim]… and {len(structure) - 20} more[/dim]")
    else:
        console.print("\n[dim]No functions or classes detected.[/dim]")

    # Related files
    if related_files:
        console.print(f"\n[bold]Related files:[/bold]")
        for fname_short, fpath, score in related_files:
            bar = "█" * int(score * 10)
            console.print(f"  {score:.2f} {bar:10s}  {fname_short}  [dim]{fpath}[/dim]")
    else:
        console.print("\n[dim]No related files found.[/dim]")

    # Content preview
    console.print(f"\n[bold]Content preview:[/bold]")
    preview_lines = full_content.splitlines()[:30]
    console.print("\n".join(preview_lines))
    if len(full_content.splitlines()) > 30:
        console.print(f"[dim]… ({len(full_content.splitlines())} total lines indexed)[/dim]")

    console.print()


# ── benchmark ─────────────────────────────────────────────────────────────────

@main.command()
@click.option("--queries", "-q", default=None, metavar="FILE",
              help="JSON file with custom query list (array of strings).")
@click.option("--output", "-o", default=None, metavar="FILE",
              help="Save report to a JSON file.")
@click.option("--limit", "-n", default=5, show_default=True,
              help="Results to retrieve per query.")
def benchmark(queries: str | None, output: str | None, limit: int):
    """Measure Synapse retrieval quality and get a shareable score.\n
    \b
    Runs a set of preset queries against your index and scores how well
    Synapse retrieves relevant code. Share the results to show Synapse works.

    Examples:
      synapse benchmark
      synapse benchmark --queries my_queries.json
      synapse benchmark --output results.json
    """
    from synapse.benchmark import run_benchmark, load_custom_queries, PRESET_QUERIES

    # Load queries
    custom_queries = None
    if queries:
        try:
            custom_queries = load_custom_queries(queries)
            console.print(f"[dim]Loaded {len(custom_queries)} custom queries from {queries}[/dim]")
        except Exception as exc:
            console.print(f"[red]Error loading query file: {exc}[/red]")
            sys.exit(1)

    query_list = custom_queries or PRESET_QUERIES
    console.print(f"\n[bold cyan]Synapse Benchmark[/bold cyan] — {len(query_list)} queries\n")

    # Run with progress
    report = None
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Running queries…", total=len(query_list))

        # Patch progress into benchmark (simple approach: run and update after)
        from synapse.benchmark import run_benchmark as _run
        report = _run(custom_queries=custom_queries, limit=limit)
        progress.update(task, completed=len(query_list))

    # ── Results table ─────────────────────────────────────────────────────────
    table = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 1))
    table.add_column("Query", style="white", max_width=40)
    table.add_column("Hits", justify="center", width=5)
    table.add_column("Top Score", justify="right", width=10)
    table.add_column("Latency", justify="right", width=10)
    table.add_column("Best Match", style="dim", max_width=30)

    for r in report.results:
        score_color = "green" if r.top_score >= 0.5 else "yellow" if r.top_score >= 0.3 else "red"
        hit_str = f"[green]{r.hits}/{r.total}[/green]" if r.hits > 0 else f"[red]{r.hits}/{r.total}[/red]"
        table.add_row(
            r.query[:40],
            hit_str,
            f"[{score_color}]{r.top_score:.2f}[/{score_color}]",
            f"{r.latency_ms:.0f}ms",
            r.top_file[:30],
        )

    console.print(table)

    # ── Summary ───────────────────────────────────────────────────────────────
    score_color = "green" if report.overall_score >= 60 else "yellow" if report.overall_score >= 35 else "red"
    hit_pct = round(report.queries_with_hits / report.total_queries * 100) if report.total_queries else 0

    console.print(f"\n{'─' * 60}")
    console.print(f"  [bold]Synapse Score:[/bold]  [{score_color}][bold]{report.overall_score}/100[/bold][/{score_color}]")
    console.print(f"  Hit rate:        {hit_pct}%  ({report.queries_with_hits}/{report.total_queries} queries found results)")
    console.print(f"  Avg relevance:   {report.avg_top_score:.2f}")
    console.print(f"  Avg latency:     {report.avg_latency_ms:.0f}ms")
    console.print(f"  Index:           {report.indexed_files:,} files · {report.indexed_chunks:,} chunks")
    console.print(f"  Provider:        {report.provider}")
    console.print(f"{'─' * 60}\n")

    if report.overall_score >= 60:
        console.print("[bold green]✓ Synapse is retrieving relevant code reliably.[/bold green]")
    elif report.overall_score >= 35:
        console.print("[yellow]⚠ Retrieval is partial. Try re-indexing: synapse wipe && synapse init <path>[/yellow]")
    else:
        console.print("[red]✗ Low retrieval quality. Check that your project is fully indexed.[/red]")
        console.print("  Run: [bold]synapse status[/bold]")

    # Shareable one-liner
    console.print(
        f"\n[dim]Shareable result: "
        f"Synapse scored {report.overall_score}/100 on {report.total_queries} queries "
        f"({hit_pct}% hit rate, {report.avg_latency_ms:.0f}ms avg) "
        f"— github.com/nrkoka786/synapse[/dim]"
    )

    # Save to file if requested
    if output:
        _save_report(report, output)
        console.print(f"\n✓ Report saved to [green]{output}[/green]")

    console.print()


# ── wipe ─────────────────────────────────────────────────────────────────────

@main.command()
@click.confirmation_option(prompt="Delete the entire Synapse index? This cannot be undone.")
def wipe():
    """Delete all indexed data. Your source files are untouched."""
    metadata = MetadataStore()
    vectordb = VectorDB()
    metadata.wipe()
    vectordb.wipe()
    console.print("[bold green]✓ Synapse index wiped.[/bold green]")
    console.print("Run [bold]synapse init <path>[/bold] to rebuild.")


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_mcp_server():
    from synapse.mcp.server import run
    run()


def _print_mcp_instructions():
    console.print("\n" + "─" * 60)
    console.print("[bold]Next: connect Synapse to your AI tool[/bold]\n")
    console.print("[bold]Claude Code:[/bold]")
    console.print("  claude mcp add synapse synapse-mcp\n")
    console.print("[bold]Cursor / Continue / Windsurf[/bold] — add to MCP config:")
    mcp_entry = {"mcpServers": {"synapse": {"command": "synapse-mcp", "args": []}}}
    console.print(json.dumps(mcp_entry, indent=2))
    console.print("\n[bold green]Then restart your AI tool. Done. ✓[/bold green]\n")


def _extract_structure(content: str, language: str) -> list[tuple[str, str]]:
    """Extract function and class names from indexed content using simple regex."""
    import re
    patterns = {
        "python":     [(r"^class\s+(\w+)", "class"), (r"^(?:async )?def\s+(\w+)", "function")],
        "typescript": [(r"^(?:export\s+)?class\s+(\w+)", "class"),
                       (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function"),
                       (r"^(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(", "function")],
        "javascript": [(r"^(?:export\s+)?class\s+(\w+)", "class"),
                       (r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)", "function")],
        "go":         [(r"^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)", "function"),
                       (r"^type\s+(\w+)\s+struct", "class")],
        "rust":       [(r"^(?:pub\s+)?fn\s+(\w+)", "function"),
                       (r"^(?:pub\s+)?struct\s+(\w+)", "class")],
        "java":       [(r"^(?:public|private|protected)?\s*class\s+(\w+)", "class"),
                       (r"^(?:public|private|protected)[\w\s]*\s+(\w+)\s*\(", "function")],
    }
    rules = patterns.get(language, [])
    found = []
    seen = set()
    for line in content.splitlines():
        line = line.strip()
        for pattern, kind in rules:
            m = re.match(pattern, line)
            if m:
                name = m.group(1)
                if name not in seen:
                    seen.add(name)
                    found.append((kind, name))
    return found


def _save_report(report, path: str):
    """Save benchmark report as JSON."""
    import dataclasses
    data = {
        "overall_score": report.overall_score,
        "hit_rate_pct": round(report.queries_with_hits / report.total_queries * 100),
        "avg_top_score": report.avg_top_score,
        "avg_latency_ms": report.avg_latency_ms,
        "indexed_files": report.indexed_files,
        "indexed_chunks": report.indexed_chunks,
        "provider": report.provider,
        "queries": [
            {
                "query": r.query,
                "hits": r.hits,
                "total": r.total,
                "top_score": r.top_score,
                "avg_score": r.avg_score,
                "latency_ms": r.latency_ms,
                "top_file": r.top_file,
            }
            for r in report.results
        ],
    }
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _human_bytes(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.1f} GB"
