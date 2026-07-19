Synapse
Give Claude instant knowledge of your codebase — local, private, no cloud.



You open Claude Code and ask: "Add retry logic to my API client."

Without Synapse: Claude asks what your stack is. You paste 200 lines of code. You explain your conventions. You do this again tomorrow.

With Synapse: Claude says: "Your API client in src/api/client.ts uses Axios with your custom RetryConfig interface — matching the pattern you used in payment.ts. Here's the implementation:"

Synapse watches your project folders, indexes them locally, and connects to Claude via MCP. Claude knows your codebase without you saying a word.


Install in 2 minutes
pip install synapse-mcp

synapse init C:/Projects/myapp

Then paste one line into your Claude Desktop config. Done.


What it does
Watches your project folders — indexes code, markdown, and config files automatically
Stores everything locally — no API key required, nothing leaves your machine
Connects to Claude via MCP — works with Claude Desktop, Cursor, and any MCP client
Updates in real time — re-indexes files as you save them


Supported tools
Tool
Status
Claude Code
✅ Supported (primary target)
Cursor
✅ Supported via MCP
Continue
✅ Supported via MCP
Claude Desktop chat
🔜 Coming in v0.2
Any MCP client
✅ Standard MCP protocol



Supported file types
.py .ts .tsx .js .jsx .go .rs .java .kt .rb .php .cs .swift .cpp .c .h .sh .ps1 .sql .tf .md .json .yaml .toml .env .graphql .proto · Dockerfile · Makefile · and more


Connect to Claude Code
After running synapse init <path>, register Synapse as an MCP server:

claude mcp add synapse synapse-mcp

That's it. Restart claude and run /mcp to confirm synapse shows connected · 2 tools.

Claude Desktop chat support is planned for v0.2 via SSE transport. Track progress in #12.


CLI reference
synapse init <path>      # Index a folder (run this first)

synapse status           # Show what's indexed

synapse search <query>   # Search from the terminal

synapse wipe             # Delete the local index


Configuration
Synapse works out of the box with no config file required.
To customize, create ~/.synapse/config.toml:

[synapse]

watch_paths = ["C:/Projects/myapp", "C:/Projects/clientwork"]

ignore_patterns = ["node_modules", ".git", "dist", "*.pyc"]

[embedding]

provider = "local"   # "local" (default, free, private) or "openai"

chunk_size = 512

chunk_overlap = 64

Local embeddings (default): Uses nomic-embed-text-v1.5 via sentence-transformers.
Downloads ~400MB on first run. Free. Nothing leaves your machine.

OpenAI embeddings (optional): Set provider = "openai" and OPENAI_API_KEY env var.
Slightly better quality for natural language queries. Costs ~$0.00 for personal use.


How it works
Your files → Synapse watches → Chunks text → Embeds locally → Stores in LanceDB

                                                                       ↓

Claude Desktop ←── MCP query ←── Synapse MCP server ←── Semantic search

synapse init walks your project and indexes every supported file
The file watcher triggers incremental re-indexing on every save
When you open Claude Desktop, the synapse-mcp server is available as a connected tool
Claude calls recall("your question") automatically before answering
Relevant code snippets are injected into Claude's context window

No round trips to external servers. No accounts. No rate limits.


FAQ
Does my code leave my machine?
No. With the default local embedding provider, every computation happens on your machine. The only network call is the initial model download (~400MB, cached permanently after that).

What if I use the openai provider?
Your code text is sent to OpenAI's API for embedding. If you work on sensitive or proprietary code, use the default local provider.

How is this different from Cursor's built-in indexing?
Cursor's index lives inside Cursor only. Synapse works with Claude Desktop, Cursor, Continue, and any other MCP-compatible client — all from one index.

How is this different from ChatGPT Memory?
ChatGPT Memory is locked to ChatGPT and stored on OpenAI's servers. Synapse works with any AI tool and stores everything locally.

Will it index my .env files or secrets?
Yes — it indexes .env files if they're in your watch path. If you don't want this, add .env to the ignore_patterns list in your config.

Can I inspect what's in the index?
Yes: synapse status shows counts, and synapse search <query> lets you query it directly.

How do I remove a project from the index?
Run synapse wipe to clear everything. Then run synapse init again with only the paths you want.


Requirements
Python 3.10+
1 GB free disk space (for the embedding model cache)
Claude Desktop (or any MCP client)


Contributing
Synapse is MIT-licensed and welcomes contributions.

Good first issues:

Add support for a new file type in synapse/ingestion/reader.py
Improve chunking for a specific language
Write integration tests

To contribute:

git clone https://github.com/nrkoka786/synapse

cd synapse

pip install -e ".[dev]"

pytest tests/

See CONTRIBUTING.md for guidelines.


Roadmap
Core filesystem indexing
Claude Code MCP integration
Local embeddings (no API key)
File watcher (incremental re-indexing)
Claude Desktop chat support (SSE transport) — v0.2
Git log ingestion (commit messages + PR descriptions)
Markdown + PDF document indexing
synapse search TUI with rich output
Windows installer (.exe)
macOS App
Synapse Cloud (encrypted cross-device sync) — planned
Team Synapse (shared org context) — planned


License
MIT © 2026 NR · github.com/nrkoka786/synapse

