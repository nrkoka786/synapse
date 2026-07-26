# Synapse
**Give any AI instant knowledge of your codebase — local, private, no cloud.**

> Works with Claude, Cursor, Continue, Windsurf, and any MCP-compatible AI tool.

---

You open your AI coding tool and ask: "Add retry logic to my API client."

**Without Synapse:** The AI asks what your stack is. You paste 200 lines of code. You explain your conventions. You do this again tomorrow.

**With Synapse:** It says: *"Your API client in `src/api/client.ts` uses Axios with your custom `RetryConfig` interface — matching the pattern you used in `payment.ts`. Here's the implementation:"*

Synapse watches your project folders, indexes them locally, and connects to your AI tool via MCP. It knows your codebase without you saying a word.

---

## Install in 2 minutes

```bash
pip install synapse-mcp

synapse init C:/Projects/myapp
```

Then paste one line into your Claude / Cursor / Continue config. Done.

---

## What it does

- **Watches your project folders** — indexes code, markdown, and config files automatically
- **Stores everything locally** — no cloud, no accounts, nothing leaves your machine
- **Connects via MCP** — works with Claude Code, Cursor, Continue, Windsurf, and any MCP client
- **Updates in real time** — re-indexes files as you save them
- **Your choice of AI model** — use any embedding provider, including fully local ones

---

## Supported AI tools

| Tool | Status |
|---|---|
| Claude Code | ✅ Supported (primary target) |
| Cursor | ✅ Supported via MCP |
| Continue | ✅ Supported via MCP |
| Windsurf | ✅ Supported via MCP |
| Any MCP client | ✅ Standard MCP protocol |
| Claude Desktop chat | 🔜 Coming in v0.3 (SSE transport) |

---

## Embedding providers

Synapse works with **five embedding providers** — pick the one that fits your workflow.
All providers output compatible vectors and share the same local index.

| Provider | Install | Key required | Notes |
|---|---|---|---|
| `local` | *(default)* | none | nomic-embed-text, ~400MB download, fully private |
| `ollama` | *(no extra)* | none | Any model you've pulled; needs `ollama serve` |
| `openai` | `pip install .[openai]` | `OPENAI_API_KEY` | text-embedding-3-small, best quality |
| `gemini` | `pip install .[gemini]` | `GEMINI_API_KEY` | text-embedding-004, free 1,500 req/day |
| `cohere` | `pip install .[cohere]` | `COHERE_API_KEY` | embed-english-v3.0, generous free tier |

Switch providers in `~/.synapse/config.toml`:

```toml
[embedding]
provider = "ollama"          # local · ollama · openai · gemini · cohere
model = "nomic-embed-text"   # any model supported by your chosen provider
```

> **Note:** If you switch providers, run `synapse wipe` then `synapse init` to re-index.

---

## Supported file types

`.py .ts .tsx .js .jsx .go .rs .java .kt .rb .php .cs .swift .cpp .c .h .sh .ps1 .sql .tf .md .json .yaml .toml .env .graphql .proto` · Dockerfile · Makefile · and more

---

## Connect to Claude Code

After `synapse init <path>`, register Synapse as an MCP server:

```bash
claude mcp add synapse synapse-mcp
```

Restart Claude and run `/mcp` to confirm `synapse` shows **connected · 2 tools**.

---

## Connect to Cursor / Continue / Windsurf

Add to your MCP config (`.cursor/mcp.json`, `.continue/config.json`, etc.):

```json
{
  "mcpServers": {
    "synapse": {
      "command": "synapse-mcp",
      "args": []
    }
  }
}
```

---

## CLI reference

```bash
synapse init <path>      # Index a folder (run this first)
synapse status           # Show what's indexed
synapse search <query>   # Search from the terminal
synapse wipe             # Delete the local index
```

---

## Configuration

Synapse works out of the box with no config file. To customize, create `~/.synapse/config.toml`
(or copy `synapse.toml.example`):

```toml
[synapse]
watch_paths = ["C:/Projects/myapp", "C:/Projects/clientwork"]
ignore_patterns = ["node_modules", ".git", "dist", "*.pyc"]

[embedding]
provider = "local"    # local · ollama · openai · gemini · cohere
chunk_size = 512
chunk_overlap = 64
```

See `synapse.toml.example` for the full provider reference with all options.

---

## How it works

```
Your files → Synapse watches → Chunks text → Embeds locally → Stores in LanceDB
                                                                       ↓
Your AI tool ←── MCP query ←── Synapse MCP server ←── Semantic search
```

1. `synapse init` walks your project and indexes every supported file
2. The file watcher triggers incremental re-indexing on every save
3. Your AI tool calls `recall("your question")` automatically before answering
4. Relevant code snippets are injected into the AI's context window

No round trips to external servers. No accounts. No rate limits.

---

## FAQ

**Does my code leave my machine?**
With `local` or `ollama` providers, every computation happens on your machine. With cloud providers (`openai`, `gemini`, `cohere`), only the text is sent for embedding — your index stays local.

**How is this different from Cursor's built-in indexing?**
Cursor's index lives inside Cursor only. Synapse builds one index that works across Claude, Cursor, Continue, Windsurf, and any future MCP client.

**How is this different from ChatGPT Memory?**
ChatGPT Memory is locked to ChatGPT and stored on OpenAI's servers. Synapse works with any AI tool and stores everything locally.

**Can I use a locally-running AI model?**
Yes — use the `ollama` provider with any model you've pulled via `ollama pull`. Nothing leaves your machine.

**Will it index my `.env` files or secrets?**
Yes, unless you add `.env` to `ignore_patterns` in your config.

**Can I inspect what's in the index?**
Yes: `synapse status` shows counts, and `synapse search <query>` lets you query it directly.

**How do I switch embedding providers?**
Change `provider` in `~/.synapse/config.toml`, then run `synapse wipe` and `synapse init` to rebuild the index with the new provider.

---

## Requirements

- Python 3.10+
- 1 GB free disk space (for local embedding model cache)
- Any MCP-compatible AI tool (Claude Code, Cursor, Continue, Windsurf, etc.)

---

## Contributing

Synapse is MIT-licensed and welcomes contributions.

**Good first issues:**
- Add support for a new file type in `synapse/ingestion/reader.py`
- Improve chunking for a specific language
- Write integration tests
- Add a new embedding provider in `synapse/embedding/`

```bash
git clone https://github.com/nrkoka786/synapse
cd synapse
pip install -e ".[dev]"
pytest tests/
```

See `CONTRIBUTING.md` for guidelines.

---

## Roadmap

- [x] Core filesystem indexing
- [x] Claude Code MCP integration
- [x] Local embeddings (no API key)
- [x] File watcher (incremental re-indexing)
- [x] Multi-provider embeddings (Ollama, Gemini, Cohere) — **v0.2**
- [ ] Claude Desktop chat support (SSE transport) — v0.3
- [ ] Git log ingestion (commit messages + PR descriptions)
- [ ] Markdown + PDF document indexing
- [ ] `synapse search` TUI with rich output
- [ ] Windows installer (.exe)
- [ ] macOS App
- [ ] Synapse Cloud (encrypted cross-device sync) — planned
- [ ] Team Synapse (shared org context) — planned

---

## License

MIT © 2026 NR · [github.com/nrkoka786/synapse](https://github.com/nrkoka786/synapse)
