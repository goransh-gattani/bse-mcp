"""MCP wiring and the `bse-mcp` command.

    bse-mcp            run the server over stdio (what Claude Desktop / Claude Code launch)
    bse-mcp --diag     try every way of reaching BSE from this network and print what came back
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
tools.get_market_depth.__doc__ = "Top-5 bids and asks (price and quantity) with totals for one BSE scrip."
tools.get_peers.__doc__ = ("BSE's peer group for a scrip: each peer's code, LTP, change %, PE, PB, EPS, revenue and PAT "
                           "(Rs Cr), OPM, NPM, 52-week range and the quarter those results are from.")
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

for _fn in (tools.search_scrips, tools.get_quote, tools.get_market_depth, tools.get_peers, tools.get_financials,
            tools.get_announcements, tools.download_announcement_pdf, tools.list_scrips, tools.call_bse_api):
    _tool(_fn)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bse-mcp", description="MCP server for live BSE India data (unofficial).")
    parser.add_argument("--version", action="version", version=f"bse-mcp {__version__}")
    parser.add_argument("--diag", action="store_true", help="try every way of reaching BSE from this network, print the results, and exit")
    args = parser.parse_args(argv)
    if args.diag:
        print(bse.diagnose())
        return 0
    server.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
