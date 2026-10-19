# bse-mcp

An [MCP](https://modelcontextprotocol.io) server that gives Claude live data from **BSE India** (Bombay Stock Exchange) by scrip code: price and ratios, market depth, peers, quarterly P&L with derived EBITDA and margins, corporate announcements with PDF links, and a security search. Ask Claude "what did ABB India report last quarter?" and it looks it up.

Unofficial. Not affiliated with BSE. It reads the same public endpoints the bseindia.com pages use; they can change without notice, and the data is BSE's (see [Data and terms](#data-and-terms)).

## Tools

| Tool | What it returns |
|---|---|
| `search_scrips(query)` | Scrip codes matching a name, symbol, ISIN or code fragment. Start here. |
| `get_quote(scripcode)` | LTP and change, day / 52-week ranges, price band, volume, delivery %, market cap, EPS / PE / PB / ROE / margins (standalone and consolidated), group, sector, flags (ASM/GSM). |
| `get_market_depth(scripcode)` | Top-5 bids and asks with totals. |
| `get_peers(scripcode)` | BSE's peer table: price, PE, PB, revenue, PAT, margins, 52-week range. |
| `get_financials(scripcode, quarters=5, upto=None)` | Quarterly P&L as filed, newest first, quarters named `Q1 FY27`; derived EBITDA, EBITDA / PBT / PAT margins and tax rate. The latest filed quarter is detected automatically. |
| `get_announcements(scripcode, months=12, category="all", page=1)` | Filings from BSE's announcements feed with PDF links; `category="results"` for financial results only. |
| `download_announcement_pdf(attachment, save_dir, filename=None)` | Saves a filing's PDF (Python server only). |
| `list_scrips(segment, status, group, name_contains, scripcode, limit)` | BSE's List of Securities, filtered. |
| `call_bse_api(endpoint, params, scripcode, quarter)` | Any of the 23 documented endpoints, raw, for whatever the tools above don't shape. |

## Install

BSE blocks most datacenter IPs, so the server runs where BSE will answer: on your own computer, or in your own Cloudflare Worker. Pick one.

### Claude Desktop or Claude Code, on your computer (most reliable)

**One command** installs everything and registers the server with Claude Desktop (and Claude Code, if you have it):

```bash
# macOS / Linux
curl -LsSf https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.sh | sh
```

```powershell
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/goransh-gattani/bse-mcp/main/install.ps1 | iex"
```

It installs [uv](https://docs.astral.sh/uv/) if needed (uv brings its own Python, so an old system Python doesn't matter), installs bse-mcp, checks that BSE answers from your network, and adds a `bse` entry to Claude Desktop's config without touching your other servers (the previous file is kept as `.bak`). Then quit Claude Desktop completely and reopen it. Re-run the same command to upgrade.

Already installed bse-mcp another way? `bse-mcp setup` does just the registration step.

**By hand**, if you prefer:

Needs Python 3.10+. macOS's built-in Python is 3.9, so the simplest route is [uv](https://docs.astral.sh/uv/), which fetches a recent Python just for this tool:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh                 # once; then reopen the terminal
uv tool install --python 3.12 "bse-mcp[chrome] @ git+https://github.com/goransh-gattani/bse-mcp"
bse-mcp --diag                                                  # should show HTTP 200
which bse-mcp                                                   # full path, for the config below
```

With Python 3.10+ already installed, `pip install "bse-mcp[chrome] @ git+https://github.com/goransh-gattani/bse-mcp"` works too (`pip install "bse-mcp[chrome]"` once it is on PyPI). `[chrome]` adds curl_cffi, which makes BSE far less likely to refuse.

Claude Code:

```bash
claude mcp add bse -- bse-mcp
```

Claude Desktop: Settings → Developer → Edit Config, add the server with the full path from `which bse-mcp` (the app doesn't see your terminal's PATH), then quit (⌘Q) and reopen the app:

```json
{ "mcpServers": { "bse": { "command": "/Users/you/.local/bin/bse-mcp" } } }
```

`uvx` works too: `"command": "uvx", "args": ["--from", "bse-mcp[chrome]", "bse-mcp"]`.

### claude.ai, through your own Cloudflare Worker

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/goransh-gattani/bse-mcp/tree/main/worker)

Or from a checkout: `cd worker && npx wrangler login && npx wrangler deploy`. Either way you get a URL like `https://bse-mcp.<you>.workers.dev`. Then in claude.ai: **Settings → Connectors → Add custom connector**, URL `https://bse-mcp.<you>.workers.dev/mcp`, no authentication. Enable it in a chat.

Anyone who knows the URL can call it (the data is public; the cost is your Worker's free quota, 100k requests a day). To restrict it set a `MCP_TOKEN` variable on the Worker; the server then requires `Authorization: Bearer <token>`. Claude Code can send that (`claude mcp add --transport http bse <url> --header "Authorization: Bearer <token>"`); claude.ai's custom connectors expect OAuth rather than a fixed token, so leave it unset for claude.ai.

The Worker has the same tools except `download_announcement_pdf`; `get_announcements` gives a `pdf_download_url` on the Worker instead. BSE sometimes blocks Cloudflare's IP ranges; when it does the tools say so, and the Python server from a home network is the fallback.

### Just trying it

A demo instance runs at `https://bse-proxy.goransh-gattani.workers.dev/mcp` (add it as a custom connector). It is shared, unmonitored and on a free quota, so don't build on it: deploy your own.

## If BSE refuses

The tools answer with the cause: `BSE refused ... (HTTP 403)`. From a computer run `bse-mcp --diag`; it tries each HTTP client (curl_cffi with Chrome's TLS fingerprint, urllib, curl) against BSE and prints what came back. Installing `curl_cffi` fixes most refusals. From a Worker, BSE is blocking Cloudflare at the moment; retry later or use the Python server.

## Data and terms

- Figures are what BSE publishes: quotes are delayed as BSE delays them; financials are as originally filed (later restatements are not applied) and labelled Rs million by BSE for most companies; derived rows (EBITDA, margins) are computed here and marked as such.
- The quarter-id scheme (126 = Jun-25, one step per quarter) was verified on one company's filings; quarter names in results are taken from BSE's own period-end dates, so they stay right even if the scheme drifts.
- The data belongs to BSE and its use is governed by [BSE's terms](https://www.bseindia.com/). This project only fetches it for you, the way your browser would; it grants no rights to redistribute it. Not investment advice.

## Development

```bash
pip install -e ".[test]" && pytest            # Python tools and MCP wiring, against recorded BSE responses
node --test worker/test/worker.test.mjs        # the Worker, same fixtures
```

The tests use responses recorded from BSE (shapes and values, ABB India, Oct 2026) and never call BSE, so they prove parsing and the protocol, not that BSE still answers. A release is a tag `vX.Y.Z` matching `pyproject.toml`; `publish.yml` builds and uploads to PyPI via trusted publishing.

The tool logic is in `src/bse_mcp/tools.py` (plain functions), BSE access in `src/bse_mcp/bse.py`, MCP wiring in `src/bse_mcp/server.py`, and the same tools in JavaScript in `worker/worker.js`. Companion project: [bse-automation](https://github.com/goransh-gattani/bse-automation) (a browser UI for the same endpoints and a Postman collection documenting them).

## License

MIT.
