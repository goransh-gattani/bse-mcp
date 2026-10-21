"""MCP wiring and the `bse-mcp` command.

    bse-mcp            run the server over stdio (what Claude Desktop / Claude Code launch)
    bse-mcp --diag     try every way of reaching BSE from this network and print what came back
    bse-mcp setup      register with Claude Desktop and Claude Code, and install the trading skills
"""

from __future__ import annotations

import argparse
import functools
import sys
from importlib.metadata import PackageNotFoundError, version

from . import bse, tools
from .tools import ArgError

try:  # mcp 2.x: only ToolError messages reach the model; anything else becomes "Error executing tool"
    from mcp.server.mcpserver import MCPServer as _Server
    from mcp.server.mcpserver.exceptions import ToolError
except ImportError:  # mcp 1.x passes every exception's message through
    from mcp.server.fastmcp import FastMCP as _Server
    from mcp.server.fastmcp.exceptions import ToolError

try:
    __version__ = version("bse-mcp")
except PackageNotFoundError:  # running from a checkout
    __version__ = "0.0.0"

INSTRUCTIONS = (
    "Live data from BSE India (Bombay Stock Exchange) by scrip code, read from the public endpoints behind "
    "bseindia.com. Start with search_scrips when you only have a company name; the 5-6 digit code it returns is "
    "what every other tool takes. Amounts from get_financials are as BSE labels them (Rs million for most "
    "companies, as originally filed). Unofficial: not affiliated with BSE."
)

server = _Server("bse", instructions=INSTRUCTIONS)


def _tool(fn):
    """Register a tools.* function, turning its errors into ToolError so the message reaches the model."""

    @functools.wraps(fn)  # keeps the signature, which MCP turns into the tool's input schema
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ArgError, bse.BseError) as exc:
            raise ToolError(str(exc)) from None

    return server.tool(name=fn.__name__, description=fn.__doc__)(wrapped)


# Descriptions double as the docstrings Claude reads; keep them about what comes back and which argument to pass.
tools.search_scrips.__doc__ = ("Find BSE scrip codes by company name, symbol, ISIN or code fragment (e.g. 'reliance', 'ABB', "
                               "'INE117A01022'). Returns up to 20 matches: scripcode, symbol, name, isin, market. Use the "
                               "scripcode in the other tools.")
tools.get_quote.__doc__ = ("Live price and key facts for one BSE scrip: LTP, change, day/52-week range, volume, delivery %, "
                           "market cap, EPS/PE/PB/ROE/margins (standalone and consolidated), group, sector/industry, ISIN, "
                           "flags (ASM/GSM etc.). scripcode: the 5-6 digit BSE code.")
tools.get_session_status.__doc__ = ("Whether a BSE scrip's price is from today's session. BSE returns a last price for every scrip at all "
                                    "times (after hours, holidays, suspended scrips), so this compares the price's own timestamp with today "
                                    "in IST. status: live, closed_after_session, pre_open, awaiting_open, market_closed (nothing traded "
                                    "today), stock_not_trading (the market traded but this scrip didn't), or unknown. data_as_of is the "
                                    "price's timestamp. get_quote, analyze_fundamentals and analyze_prices(scripcode) include the same block.")
tools.get_market_depth.__doc__ = "Top-5 bids and asks (price and quantity) with totals for one BSE scrip."
tools.get_peers.__doc__ = ("BSE's peer group for a scrip: each peer's code, LTP, change %, PE, PB, EPS, revenue and PAT "
                           "(Rs Cr), OPM, NPM, 52-week range and the quarter those results are from.")
tools.get_price_history.__doc__ = ("Daily closing prices and traded quantity on BSE for one scrip over the last 12 months, oldest "
                                   "first (dates, closes, volumes), from BSE's price chart. No daily open/high/low. For indicators, "
                                   "call analyze_prices with the scripcode instead of copying these numbers.")
tools.get_financials.__doc__ = ("Quarterly P&L from BSE's results filings, newest first, with derived EBITDA, margins and tax "
                                "rate. quarters: how many to return (1-16). upto: the newest quarter to include, like "
                                "'Q1 FY27'; by default the latest quarter BSE has results for is detected. Values are as "
                                "originally filed; expenses are negative; BSE labels the amounts Rs million for most companies.")
tools.get_announcements.__doc__ = ("Corporate announcements and filings for a scrip from BSE's announcements feed, newest "
                                   "first, with PDF links. months: look back 1-12 months (BSE returns nothing for longer "
                                   "spans). category: 'all' or 'results' (financial results only). page: 1-based, about 50 "
                                   "rows per page; 'total' says how many exist.")
tools.download_announcement_pdf.__doc__ = ("Save an announcement's PDF (the 'attachment' from get_announcements) into "
                                           "save_dir, optionally under filename, and return the file path.")
tools.list_scrips.__doc__ = ("List BSE securities from the List of Securities page, filtered by segment (Equity, EQT0, MF, "
                             "HS, MB, 'Preference Shares', 'Debentures and Bonds', 'Equity - Institutional Series', "
                             "'Commercial Papers', 'Government Securities', 'Certificate of Deposit', 'Treasury Bills'), "
                             "status (Active/Suspended/Delisted/''), group code (A, B, T, ...), a name fragment, or one exact "
                             "code. Returns up to `limit` rows and the total count. Big segments without a name filter are "
                             "several MB on BSE's side; add a filter when you can.")
tools.call_bse_api.__doc__ = ("Call any documented BSE endpoint and return its raw decoded JSON. endpoint is one of: "
                              + ", ".join(bse.ENDPOINTS) + ". Default params are filled from scripcode and quarter (a BSE "
                              "quarter id like '130.00', or 'Q1 FY27'); anything in params overrides them.")

tools.analyze_fundamentals.__doc__ = ("Computed fundamentals for a BSE scrip from its quarterly filings: revenue, EBITDA, PBT, PAT, EPS "
                                      "with YoY and QoQ growth (matched by period, not by position), margins and margin change, cost "
                                      "structure as % of revenue, interest coverage, tax rate, other income as % of PBT, TTM totals and "
                                      "TTM growth, and TTM P/E and price/sales from the live price. quarters: how many to fetch "
                                      "(8 gives TTM and its growth). Banks file a different format, so for them (kind='bank') you get NII, PPOP, "
                                      "cost-to-income, provisions, gross/net NPA %, NPA coverage, RoA and CET1 instead of EBITDA and cost "
                                      "structure. Use this instead of doing the arithmetic yourself.")
tools.analyze_prices.__doc__ = ("Technical indicators on daily prices. Either pass scripcode to use BSE's daily closes and volumes for "
                                "the last 12 months, or pass your own daily series oldest first (e.g. candles from NSE's price-history "
                                "MCP server): closes, plus dates, highs, lows, volumes. Gives returns, CAGR, volatility, max drawdown, "
                                "SMA 20/50/200, EMA 12/26/50, MACD, RSI(14), Bollinger(20,2), 52-week position, SMA50/200 trend, recent "
                                "swing highs/lows, Fibonacci levels, RSI divergence, volume vs its 20-day average, and price_jumps "
                                "(possible unadjusted splits); with highs and lows also ATR(14), ADX/DI, stochastic, chandelier exit and "
                                "classic pivots. timeframe='weekly' rebuilds weekly bars from the daily series. entry_date (+ side "
                                "long/short) adds trailing-stop levels since entry: ATR trail, chandelier, latest swing low/high. "
                                "About 260 daily bars covers everything except 3y/5y returns.")
tools.position_size.__doc__ = ("Position size, risk/reward and Indian trading costs for one trade. capital (Rs), entry, and either "
                               "stop or atr (+ atr_multiplier, default 2) to place the stop from volatility. risk_pct of capital "
                               "(default 1), side long/short, optional target, leverage, max_position_pct (single-stock cap, "
                               "default 20), win_rate and avg_win_loss for expected value and Kelly, segment delivery/intraday, "
                               "exchange NSE/BSE, your broker's brokerage_per_order / brokerage_pct / dp_charge. Returns shares, "
                               "which limit decided them, loss at stop and gain at target net of STT, exchange, SEBI, stamp duty, "
                               "brokerage and GST, net reward:risk, breakeven move and Kelly fractions.")

tools.record_analysis.__doc__ = ("Record a skill's verdict on a stock in the local journal (SQLite), so the skills can later be judged on "
                                 "what the price did next. Call it once per verdict, at the end of an analysis. skill: the skill's name "
                                 "(e.g. 'bse-mcp-trading-toolkit'). action: buy, sell (bearish: short, or exit a long), hold or avoid. "
                                 "entry defaults to the live price; stop and target are prices; horizon_days: trading days to judge "
                                 "the call over (default 20). confidence 0-1, a one-line rationale, and model (your model name) if known. "
                                 "nse_symbol when it differs from BSE's symbol. The live price and session status are saved with it.")

for _fn in (tools.search_scrips, tools.get_quote, tools.get_market_depth, tools.get_peers, tools.get_price_history, tools.get_financials,
            tools.get_announcements, tools.download_announcement_pdf, tools.list_scrips, tools.call_bse_api,
            tools.analyze_fundamentals, tools.analyze_prices, tools.position_size, tools.get_session_status, tools.record_analysis):
    _tool(_fn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bse-mcp", description="MCP server for live BSE India data (unofficial). "
                                     "With no command it runs the server over stdio, which is what Claude launches.")
    parser.add_argument("--version", action="version", version=f"bse-mcp {__version__}")
    parser.add_argument("--diag", action="store_true", help="try every way of reaching BSE from this network, print the results, and exit")
    sub = parser.add_subparsers(dest="cmd")
    setup = sub.add_parser("setup", help="register this server with Claude Desktop and Claude Code, and install the trading skills")
    setup.add_argument("--no-desktop", action="store_true", help="don't touch the Claude Desktop config")
    setup.add_argument("--no-code", action="store_true", help="don't touch Claude Code (no server registration, no skills)")
    setup.add_argument("--no-skills", action="store_true", help="don't install the trading skills into Claude Code")
    snap = sub.add_parser("snapshot", help="journal: record quote and price analysis for a watchlist, plus NSE daily candles")
    snap.add_argument("scrips", nargs="*", help="scrip codes, optionally CODE:NSESYMBOL (default: the watchlist file)")
    snap.add_argument("--watchlist", help="file of 'scripcode [NSE symbol]' lines (default ~/.bse-mcp/watchlist.txt)")
    snap.add_argument("--no-candles", action="store_true", help="skip fetching NSE candles")
    score = sub.add_parser("score", help="journal: score recorded verdicts whose horizon has passed, against NSE daily candles")
    score.add_argument("--no-fetch", action="store_true", help="use only candles already in the journal")
    sub.add_parser("report", help="journal: how each skill's scored verdicts did")
    args = parser.parse_args(argv)
    if args.diag:
        print(bse.diagnose())
        return 0
    if args.cmd == "setup":
        from . import setup_claude
        try:
            for line in setup_claude.run(desktop=not args.no_desktop, code=not args.no_code, skills=not (args.no_code or args.no_skills)):
                print(line)
        except setup_claude.SetupError as exc:
            print(f"bse-mcp setup: {exc}", file=sys.stderr)
            return 1
        return 0
    if args.cmd in ("snapshot", "score", "report"):
        return _journal(args)
    server.run()
    return 0


def _journal(args) -> int:
    from pathlib import Path

    from . import journal, nse

    history = None if getattr(args, "no_candles", False) or getattr(args, "no_fetch", False) else nse.stock_history
    now = tools._now()
    with journal.connect() as conn:
        if args.cmd == "snapshot":
            if args.scrips:
                watch = [(c.split(":")[0], (c.split(":") + [None])[1]) for c in args.scrips]
            else:
                path = Path(args.watchlist or Path.home() / ".bse-mcp" / "watchlist.txt").expanduser()
                if not path.is_file():
                    print(f"bse-mcp snapshot: no scrips given and no watchlist at {path} (lines of 'scripcode [NSE symbol]')", file=sys.stderr)
                    return 1
                watch = journal.read_watchlist(path)
            lines = journal.snapshot(conn, watch, now, tools.get_quote, lambda c: tools.analyze_prices(scripcode=c), history)
        elif args.cmd == "score":
            lines = journal.score(conn, now, history) or ["nothing to score"]
        else:
            lines = journal.format_report(journal.report(conn))
    print(f"journal: {journal.db_path()}")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
