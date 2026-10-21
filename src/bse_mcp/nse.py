"""Daily candles from NSE's public bhavcopy MCP server, for the journal's snapshots and scoring.

The server (https://mcp.nseindia.in/bhavcopy/cm/mcp) speaks MCP over Streamable HTTP with no sign-in.
Its sessions don't survive across its backends: about half the calls made on a fresh session come back
"Session not found". So every call opens its own session and is retried a few times.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

URL = "https://mcp.nseindia.in/bhavcopy/cm/mcp"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


class NseError(Exception):
    """NSE's server didn't answer usefully after retries."""


def _post(body: dict, session: str | None = None, timeout: float = 30) -> tuple[str | None, str]:
    headers = dict(HEADERS, **({"Mcp-Session-Id": session} if session else {}))
    req = urllib.request.Request(URL, json.dumps(body).encode(), headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.headers.get("Mcp-Session-Id"), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return None, exc.read().decode("utf-8", "replace")


def _message(text: str) -> dict:
    """The JSON-RPC message in a reply, whether sent as plain JSON or as a server-sent event."""
    data = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
    try:
        return json.loads(data[-1] if data else text)
    except ValueError:
        return {}


def call(tool: str, arguments: dict, attempts: int = 6, pause: float = 1.0, timeout: float = 30) -> dict:
    """Call one tool on NSE's server and return its decoded JSON result."""
    last = "no attempt"
    for attempt in range(attempts):
        try:
            session, _ = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                           "clientInfo": {"name": "bse-mcp", "version": "1"}}}, timeout=timeout)
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, session, timeout)
            _, text = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": arguments}},
                            session, timeout)
        except (OSError, urllib.error.URLError) as exc:  # timeouts, refused connections
            last = f"{type(exc).__name__}: {exc}"
        else:
            msg = _message(text)
            result = msg.get("result")
            if result is not None:
                content = "".join(c.get("text", "") for c in result.get("content") or [])
                if result.get("isError"):
                    raise NseError(f"NSE {tool}: {content[:300]}")
                try:
                    return json.loads(content)
                except ValueError:
                    raise NseError(f"NSE {tool} did not return JSON: {content[:300]}") from None
            last = str(msg.get("message") or msg.get("error") or text)[:200]
        if attempt + 1 < attempts:
            time.sleep(pause * (attempt + 1))
    raise NseError(f"NSE {tool} failed after {attempts} attempts: {last}")


def stock_history(symbol: str, bars: int = 260, end_date: str | None = None, **kw) -> list[dict]:
    """Daily EQ-series candles for an NSE symbol, oldest first, at least `bars` long when NSE has them.

    NSE returns up to 3 months per call and a next_end_date to page back from."""
    rows: dict[str, dict] = {}
    end = end_date
    for _ in range(12):  # 12 x 3 months is plenty for anything this is used for
        args = {"symbol": symbol, "months": 3, **({"endDate": end} if end else {})}
        page = call("get_stock_history", args, **kw)
        for r in page.get("data") or []:
            if r.get("series", "EQ") == "EQ" and r.get("date"):
                rows[r["date"]] = {k: r.get(k) for k in ("date", "open", "high", "low", "close", "volume")}
        end = page.get("next_end_date")
        if len(rows) >= bars or not end or not page.get("data"):
            break
    return [rows[d] for d in sorted(rows)]
