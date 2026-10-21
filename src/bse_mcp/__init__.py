"""bse-mcp: an MCP server that gives Claude live BSE India data by scrip code (unofficial)."""

from .tools import (ArgError, analyze_fundamentals, analyze_prices, position_size, call_bse_api, download_announcement_pdf, get_announcements, get_financials,  # noqa: F401
                    get_market_depth, get_peers, get_price_history, get_quote, list_scrips, search_scrips)
from .bse import BseError  # noqa: F401
