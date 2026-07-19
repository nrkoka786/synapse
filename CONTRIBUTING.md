# Contributing to Synapse

Thank you for your interest in contributing! Synapse is a small, focused project
and every contribution — bug reports, fixes, new file type support, docs — matters.

## Development setup

```bash
git clone https://github.com/nrkoka786/synapse
cd synapse
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

## Running tests

```bash
pytest tests/ -v
```

Tests that require model downloads (embedding tests) are skipped by default in CI.
To run them locally: `pytest tests/ -v --run-slow`

## Project structure

```
synapse/
├── synapse/
│   ├── config.py         # Configuration management
│   ├── daemon.py         # Core indexing + search coordinator
│   ├── cli.py            # CLI commands (click)
│   ├── ingestion/
│   │   ├── reader.py     # File reading + language detection
│   │   ├── chunker.py    # Text → overlapping chunks
│   │   └── watcher.py    # File system watcher (watchdog)
│   ├── embedding/
│   │   ├── local.py      # sentence-transformers (default)
│   │   └── openai_emb.py # OpenAI API (optional)
│   ├── store/
│   │   ├── vectordb.py   # LanceDB vector store
│   │   └── metadata.py   # SQLite file registry
│   └── mcp/
│       └── server.py     # FastMCP server (recall + context tools)
└── tests/
```

## Adding a new file type

Edit `synapse/ingestion/reader.py`:
1. Add your extension to `EXTENSION_TO_LANGUAGE`
2. Add a test in `tests/test_reader.py`

## Improving chunking for a language

Edit `synapse/ingestion/chunker.py`:
1. Add a regex pattern to `block_patterns` in `_split_code()`
2. Add a test case in `tests/test_chunker.py`

## Pull request guidelines

- Keep PRs focused: one feature or fix per PR
- Add tests for new behavior
- Run `pytest tests/` before submitting
- Update the README if you add user-facing functionality

## Reporting bugs

Open a GitHub issue with:
- Your OS and Python version
- The command you ran
- The full error output
- Your `synapse status` output (if relevant)
