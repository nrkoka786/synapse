# Changelog

All notable changes to Synapse are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Synapse uses [Semantic Versioning](https://semver.org/).

---

## [0.3.0] - 2026-07-25

### Added

- **`synapse explain <file>`** — shows a file's language, structure (functions and classes),
  chunk count, related files with relevance scores, and a content preview. Fast way to
  understand an unfamiliar module or onboard a new team member.

- **`synapse benchmark`** — runs 10 preset semantic queries against your index and produces
  a retrieval quality score (0–100). Supports `--output results.json` for saving and
  `--queries my_queries.json` for custom query sets.

- **`npx synapse-mcp`** — Node.js wrapper published to npm as
  [`synapse-mcp`](https://www.npmjs.com/package/synapse-mcp). JavaScript, Go, and Rust
  developers can now use Synapse without installing Python manually.

- **GitHub Action** (`nrkoka786/synapse@v0.3`) — reusable action that indexes your repo
  in CI and posts a context health report as a PR comment. Add one line to your workflow.

- **`synapse/benchmark.py`** — benchmark engine with preset queries, relevance scoring,
  and JSON report output.

- **`.github/workflows/synapse-ci.yml`** — Synapse indexes its own codebase on every PR.

### Changed

- `synapse/cli.py` — added `explain` and `benchmark` commands; updated `init` to use
  `_get_encoder()` from `daemon.py` for consistent provider routing across all commands.

- `synapse/daemon.py` — `_get_encoder()` now supports all five providers via `importlib`
  with friendly install-hint errors when a provider package is missing.

### Fixed

- `packages/synapse-npx/package.json` — corrected bin script paths and normalized
  repository URL (flagged by npm auto-correct on first publish).

---

## [0.2.0] - 2026-07-19

### Added

- **Ollama embedding provider** (`provider = "ollama"`) — fully local, no API key,
  no extra Python install. Requires Ollama running locally. Recommended model:
  `nomic-embed-text` (768-dim).

- **Google Gemini embedding provider** (`provider = "gemini"`) — uses
  `text-embedding-004` (768-dim). Requires `GEMINI_API_KEY`. Free tier: 1,500 req/day.
  Install: `pip install synapse-mcp[gemini]`.

- **Cohere embedding provider** (`provider = "cohere"`) — uses `embed-english-v3.0`,
  truncated to 768-dim and re-normalised. Requires `COHERE_API_KEY`. Generous free tier.
  Install: `pip install synapse-mcp[cohere]`.

- **`synapse/embedding/ollama.py`** — Ollama provider using stdlib `urllib` (no extra deps).

- **`synapse/embedding/gemini.py`** — Gemini provider using `google-genai` SDK with
  `RETRIEVAL_DOCUMENT` / `RETRIEVAL_QUERY` task types for better retrieval accuracy.

- **`synapse/embedding/cohere.py`** — Cohere provider with dimension truncation and
  re-normalisation to match Synapse's 768-dim LanceDB schema.

- **Optional dependency groups** in `pyproject.toml`:
  `[openai]`, `[ollama]`, `[gemini]`, `[cohere]`, `[all]`.

### Changed

- `synapse/daemon.py` — `_get_encoder()` refactored to route across all five providers
  using `importlib` with a clear provider table and install-hint errors.

- `synapse.toml.example` — full provider comparison table with commented config blocks
  for all five providers.

- `README.md` — new tagline (*"Give any AI instant knowledge of your codebase"*),
  provider comparison table, and setup instructions for Cursor, Continue, and Windsurf.

- `pyproject.toml` — version bumped to `0.2.0`; description updated to reflect
  multi-LLM support; keywords expanded.

### Notes

- Switching embedding providers requires rebuilding the index:
  `synapse wipe` then `synapse init <path>`.
- Default provider remains `local` — no changes needed for existing installs.

---

## [0.1.0] - 2026-07-18

### Added

- Initial release.
- Local filesystem indexing with real-time file watcher.
- Semantic search via LanceDB + `nomic-embed-text-v1.5` (local, private, ~400MB).
- OpenAI embedding provider (`text-embedding-3-small`, 768-dim).
- FastMCP server with two tools: `recall` (semantic search) and `context` (full file retrieval).
- CLI commands: `init`, `start`, `status`, `search`, `wipe`.
- Support for 40+ file types across Python, TypeScript, Go, Rust, Java, and more.
- Claude Code, Cursor, and Continue integration via standard MCP protocol.
- Configuration via `~/.synapse/config.toml`.
