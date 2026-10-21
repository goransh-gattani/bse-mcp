# bse-mcp

An [MCP](https://modelcontextprotocol.io) server that gives Claude live data from **BSE India** (Bombay Stock Exchange) by scrip code: price and ratios, market depth, peers, a year of daily prices, quarterly P&L with derived EBITDA and margins, corporate announcements with PDF links, and a security search. On top of the data it computes fundamentals, technical indicators and position sizes with Indian trading costs, and it ships nine [trading-analysis skills](#trading-skills) that put those tools to work. Ask Claude "what did ABB India report last quarter?" or "how many ABB shares can I buy with a 1% risk?" and it looks it up.

Unofficial. Not affiliated with BSE. It reads the same public endpoints the bseindia.com pages use; they can change without notice, and the data is BSE's (see [Data and terms](#data-and-terms)).

## Tools

| Tool | What it returns |
|---|---|
| `search_scrips(query)` | Scrip codes matching a name, symbol, ISIN or code fragment. Start here. |
| `get_quote(scripcode)` | LTP and change, day / 52-week ranges, price band, volume, delivery %, market cap, EPS / PE / PB / ROE / margins (standalone and consolidated), group, sector, flags (ASM/GSM). |
| `get_market_depth(scripcode)` | Top-5 bids and asks with totals. |
| `get_peers(scripcode)` | BSE's peer table: price, PE, PB, revenue, PAT, margins, 52-week range. |
| `get_price_history(scripcode)` | BSE's daily closes and traded quantity for the last 12 months, oldest first (no daily highs and lows). |
| `get_financials(scripcode, quarters=5, upto=None)` | Quarterly P&L as filed, newest first, each quarter labelled by its months (`Apr–Jun 2026`) and by Indian FY (`Q1 FY27`); derived EBITDA, EBITDA / PBT / PAT margins and tax rate. The latest filed quarter is detected automatically. |
| `analyze_fundamentals(scripcode, quarters=8)` | Computed from the filings: YoY and QoQ growth (matched by period), margins and margin change, cost structure, interest coverage, tax rate, other income as % of PBT, TTM totals and TTM growth, TTM P/E and price/sales. The filing unit is checked against BSE's Rs-crore results card instead of assumed. |
| `analyze_prices(scripcode=None, closes=None, dates, highs, lows, volumes, timeframe="daily", entry_date=None, side="long")` | Technical indicators, either on BSE's last 12 months of daily closes (`scripcode`) or on daily candles you pass in (e.g. from NSE's `nse-bhavcopy` MCP server): returns, CAGR, volatility, drawdown, SMA 20/50/200, EMA 12/26/50, MACD, RSI(14), Bollinger(20,2), 52-week position, SMA50/200 trend, swing highs and lows with RSI, Fibonacci levels and pullback targets, RSI divergence, volume vs its average, and `price_jumps` (possible unadjusted splits). With highs and lows also ATR(14), ADX/DI, stochastic, chandelier exit and pivots. `timeframe="weekly"` builds weekly bars; `entry_date` adds trailing-stop levels since the entry. |
| `position_size(capital, entry, stop or atr, risk_pct=1, target, ...)` | Shares for a trade by fixed-fractional risk, capped by capital (with leverage) and a single-stock limit, saying which limit decided; loss at stop and gain at target net of STT, exchange and SEBI charges, stamp duty, GST and your brokerage; reward:risk, breakeven move, expected value and Kelly fractions. |
| `get_announcements(scripcode, months=12, category="all", page=1)` | Filings from BSE's announcements feed with PDF links; `category="results"` for financial results only. |
| `download_announcement_pdf(attachment, save_dir, filename=None)` | Saves a filing's PDF (Python server only). |
| `list_scrips(segment, status, group, name_contains, scripcode, limit)` | BSE's List of Securities, filtered. |
| `call_bse_api(endpoint, params, scripcode, quarter)` | Any of the 23 documented endpoints, raw, for whatever the tools above don't shape. |

## Trading skills

Skills are instructions Claude follows for a kind of task. bse-mcp ships nine, adapted from Bhala Srinivash's [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) (MIT; the licence travels in each skill folder) so that every number comes from the tools above:

| Skill | For questions like |
|---|---|
| `bse-mcp-trading-toolkit` | "Analyze ABB", "should I buy X?": runs the others as one workflow |
| `bse-mcp-technical-analysis` | Trend, support and resistance, indicator dashboard, scenarios |
| `bse-mcp-multi-timeframe-analysis` | Weekly bias, daily setup, entry trigger |
| `bse-mcp-rsi-divergence` | Regular and hidden RSI divergences |
| `bse-mcp-fibonacci-trading` | Retracement zones and extension targets |
| `bse-mcp-stop-loss-strategies` | Where to put the initial stop |
| `bse-mcp-trailing-stops` | Trailing an open position from its entry date |
| `bse-mcp-position-sizing` | How many shares, within portfolio limits |
| `bse-mcp-risk-reward-ratio` | Whether a trade's R:R and expected value justify it |

They are read-only: they end in a plan for you to decide on and never place orders. Changes from the originals: the Groww and yfinance steps are replaced by this server's tools; order placement is gone; the hourly screen becomes a daily trigger (no free intraday data); and a few errors are fixed (a delivery round trip costs more than the "~0.1%" quoted, since STT alone is 0.2%; the sizing example put 36% of an account in one stock against its own 20% limit; ADX was labelled a volatility measure; leverage was said to multiply the loss at the stop; the chandelier exit was called tighter than a 2× ATR trail; a "trades needed to recover a loss" column didn't add up).

Getting them:

- **Claude Code**: `bse-mcp setup` (which the installers below run) copies them into `~/.claude/skills/`, replacing older copies of the same skills. `--no-skills` skips that.
- **Claude app** (claude.ai and the desktop app): download the zips from [`skill-zips/`](skill-zips/) and add each one under Customize → Skills → + → Create skill → Upload a skill. Skills need "Code execution and file creation" turned on in Settings → Capabilities. Skills you enable there also reach Claude Code when you're signed in to the same account, so you can then run `bse-mcp setup --no-skills`.

ATR, ADX, stochastic and the ATR-based stops need daily highs and lows, which BSE's price chart doesn't give. Connect NSE's free end-of-day server for those: in Claude Code `claude mcp add --transport http nse-bhavcopy https://mcp.nseindia.in/bhavcopy/cm/mcp`; in the Claude app, Settings → Connectors → Add custom connector with the same URL. Without it the skills use BSE's closes and say which levels they couldn't compute.

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

It installs [uv](https://docs.astral.sh/uv/) if needed (uv brings its own Python, so an old system Python doesn't matter), installs bse-mcp, checks that BSE answers from your network, adds a `bse` entry to Claude Desktop's config without touching your other servers (the previous file is kept as `.bak`), and, if you have Claude Code, registers the server there and copies in the [trading skills](#trading-skills). Then quit Claude Desktop completely and reopen it. Re-run the same command to upgrade.

Prefer double-clicking? Download [Connect-BSE-to-Claude.zip](https://github.com/goransh-gattani/bse-mcp/raw/main/Connect-BSE-to-Claude.zip), unzip it, and double-click **Connect BSE to Claude** (`.command` on Mac, `.bat` on Windows). It runs the same installer and then restarts Claude Desktop for you. The first time, macOS asks you to right-click → Open, and Windows SmartScreen may need "More info → Run anyway", because the files aren't code-signed.

Already installed bse-mcp another way? `bse-mcp setup` does just the registration and skills step (`--no-desktop`, `--no-code` and `--no-skills` leave out parts).

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

## How the calculations are done

Each analysis result carries a `definitions` block saying exactly what every figure is, so answers can be checked. In brief: EBITDA is revenue less materials, stock-in-trade purchases, inventory change, employee and other expenses; EBIT is PBT plus finance costs; TTM is the latest four consecutive quarters; YoY compares with the quarter ending 12 months earlier, found by date rather than by position; growth off a zero or negative base is left blank rather than reported as a meaningless percentage. RSI is Wilder's (checked against StockCharts' published worked example), EMAs are SMA-seeded, Bollinger bands use the population standard deviation. EV/EBITDA, P/B, ROCE and debt ratios are not computed: BSE's results endpoints give the P&L only, and the tool says so instead of estimating.

`get_price_history` and `analyze_prices(scripcode=...)` read the 12-month view of BSE's price chart: one close and BSE-only traded quantity per day, no open, high or low. Exchange histories aren't always adjusted for splits and bonuses (NSE's bhavcopy isn't), so `analyze_prices` lists any one-day move of 25% or more as `price_jumps`, to be checked against the company's announcements.

`position_size` uses the fixed-fractional rule: shares = the smallest of risk ÷ stop distance, capital × leverage ÷ entry, and the single-stock cap ÷ entry. Costs use the statutory rates for cash equity as Upstox published them in October 2026: STT 0.1% on each side for delivery and 0.025% on the sell side intraday, NSE's transaction charge 0.00307% (revised from 1 March 2026), SEBI's ₹10 a crore, stamp duty 0.015% (delivery) or 0.003% (intraday) on the buy side, and GST at 18% on brokerage and exchange and SEBI charges. BSE's transaction charge varies by scrip group, so NSE's rate stands in unless you pass `exchange_txn_rate`. Brokerage and DP charges depend on your broker: pass yours, or they count as zero and the result says so.

The formulas are the standard ones. For background on what they mean and how analysts use them, see Zerodha Varsity's [Fundamental Analysis](https://zerodha.com/varsity/module/fundamental-analysis/) and [Technical Analysis](https://zerodha.com/varsity/module/technical-analysis/) modules (Varsity's text is Zerodha's copyright and is not reproduced here).

## Data and terms

- Figures are what BSE publishes: quotes are delayed as BSE delays them; financials are as originally filed (later restatements are not applied) and labelled Rs million by BSE for most companies; derived rows (EBITDA, margins) are computed here and marked as such.
- The quarter-id scheme (126 = Jun-25, one step per quarter) was verified on one company's filings; quarter names in results are taken from BSE's own period dates, so they stay right even if the scheme drifts. `quarter` names the Indian April–March FY quarter; for companies with another financial year (ABB India reports January–December) use `period`, which gives the months.
- Indicators and ratios describe past figures. They are not forecasts or investment advice.
- The data belongs to BSE and its use is governed by [BSE's terms](https://www.bseindia.com/). This project only fetches it for you, the way your browser would; it grants no rights to redistribute it. Not investment advice.

## Development

```bash
pip install -e ".[test]" && pytest            # Python tools and MCP wiring, against recorded BSE responses
node --test worker/test/worker.test.mjs        # the Worker, same fixtures
python scripts/build_skill_zips.py             # after editing anything in src/bse_mcp/skills/
```

The tests use responses recorded from BSE (shapes and values, ABB India, Oct 2026) and never call BSE, so they prove parsing and the protocol, not that BSE still answers. A release is a tag `vX.Y.Z` matching `pyproject.toml`; `publish.yml` builds and uploads to PyPI via trusted publishing.

The tool logic is in `src/bse_mcp/tools.py` (plain functions), the calculations in `analysis.py` and `sizing.py`, BSE access in `bse.py`, MCP wiring in `server.py`, the skills in `src/bse_mcp/skills/` (zipped copies in `skill-zips/`, checked by the tests), and the same tools in JavaScript in `worker/worker.js`. Companion project: [bse-automation](https://github.com/goransh-gattani/bse-automation) (a browser UI for the same endpoints and a Postman collection documenting them).

## License

MIT. The skills are adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills), MIT, © 2026 Bhala Srinivash.
