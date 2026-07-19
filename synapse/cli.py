"""
Synapse CLI — all commands a user will type.

  synapse init <path>    Add a folder and index it
  synapse start          Start MCP server + file watcher
  synapse status         Show index statistics
  synapse search <query> Search the index from the terminal
  synapse wipe           Delete the entire local index
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
    """Synapse — Give Claude instant knowledge of your codebase.\n
    \b
    Quick start:
      synapse init C:/Projects/myapp
      (restart Claude Desktop)
      Done — Claude now knows your codebase.
    """
    pass


# ── init ─────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("path", type=click.Path(exists=True, file_okay=False, resolve_path=True))
@click.option("--force", is_flag=True, help="Re-index all files even if unchanged.")
def init(path: str, force: bool):
    """
    Add PATH to Synapse and index it immediately.

    After running this command, update your Claude Desktop config
    to include the synapse-mcp server. Synapse will print the exact
    config snippet to copy.
    """
    folder = Path(path).resolve()
    console.print(f"\n[bold cyan]Synapse v{__version__}[/bold cyan]")
    console.print(f"Initializing: [green]{folder}[/green]\n")

    # 1. Save to config
    add_watch_path(str(folder))
    console.print("✓ Added to watch list")

    # 2. Index the folder
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

    from synapse.daemon import index_file
    from synapse.config import get_embedding_config
    from synapse.embedding.local import encode as local_encode
    from synapse.embedding.openai_emb import encode as openai_encode

    cfg = get_embedding_config()
    provider = cfg.get("provider", "local")

    console.print(f"✓ Embedding provider: [bold]{provider}[/bold]")
    if provider == "local":
        console.print("  (First run downloads ~400MB model — please wait…)")

    encode_batch = openai_encode if provider == "openai" else local_encode

    indexed = 0
    skipped = 0
    errors = 0
    total_chunks = 0

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

    # Rebuild ANN index
    vectordb.rebuild_index()

    # 3. Print Claude Desktop config snippet
    _print_claude_config_instructions()


# ── start ─────────────────────────────────────────────────────────────────────

@main.command()
def start():
    """
    Start the Synapse MCP server and file watcher.

    NOTE: Claude Desktop launches synapse-mcp automatically as a subprocess
    via the MCP config. You only need to run `synapse start` manually if you
    want to test the server or use a custom MCP client.
    """
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

    # Also start MCP server in a background thread
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

    # Watch paths
    if watch_paths:
        console.print("[bold]Watching:[/bold]")
        for p in watch_paths:
            exists = "✓" if p.exists() else "[red]✗ (not found)[/red]"
            console.print(f"  {exists} {p}")
    else:
        console.print("[yellow]No watch paths configured. Run: synapse init <path>[/yellow]")

    # Index stats
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

    # Config
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
        # Show first 500 chars
        preview = content[:500] + ("…" if len(content) > 500 else "")
        console.print(preview)
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
    """Run the MCP server (called in a daemon thread from `synapse start`)."""
    from synapse.mcp.server import run
    run()


def _print_claude_config_instructions():
    """Print the Claude Desktop MCP config snippet for Windows."""
    config_path = claude_desktop_config_path()

    # Build the MCP server entry
    mcp_entry = {
        "synapse": {
            "command": "synapse-mcp",
            "args": []
        }
    }

    console.print("\n" + "─" * 60)
    console.print("[bold]Next step: connect Synapse to Claude Desktop[/bold]\n")
    console.print(f"Open this file:")
    console.print(f"  [green]{config_path}[/green]\n")
    console.print('Add this to the [bold]"mcpServers"[/bold] section:\n')
    console.print(json.dumps(mcp_entry, indent=2))
    console.print(
        "\nIf the file doesn't exist yet, create it with:\n"
        '{\n'
        '  "mcpServers": ' + json.dumps(mcp_entry, indent=4) + '\n'
        '}'
    )
    console.print("\n[bold green]Then restart Claude Desktop.[/bold green]")
    console.print("That's it — Synapse is connected. ✓\n")


def _human_bytes(n: int) -> str:
    """Convert bytes to human-readable string."""
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n / 1024:.1f} KB"
    elif n < 1024 ** 3:
        return f"{n / 1024 ** 2:.1f} MB"
    return f"{n / 1024 ** 3:.1f} GB"
