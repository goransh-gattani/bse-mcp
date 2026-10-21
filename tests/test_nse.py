"""NSE's bhavcopy MCP client: a fresh session per call, retries, and paging back through history."""
import json

import pytest

from bse_mcp import nse


class FakeNse:
    """Stands in for nse._post. `fail` makes the next N tool calls answer 'Session not found'."""

    def __init__(self, pages=None, fail=0):
        self.pages, self.fail, self.tool_calls = pages or {}, fail, []

    def __call__(self, body, session=None, timeout=30):
        if body.get("method") == "initialize":
            return "sid", "{}"
        if body.get("method") != "tools/call":
            return None, ""
        self.tool_calls.append(body["params"])
        if self.fail:
            self.fail -= 1
            return None, json.dumps({"message": "Session not found: sid"})
        args = body["params"]["arguments"]
        page = self.pages[args.get("endDate")]
        return None, "event:message\ndata:" + json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": json.dumps(page)}]}})


def row(day):
    return {"symbol": "SBIN", "series": "EQ", "date": day, "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 10}


PAGES = {None: {"data": [row("2026-10-16"), row("2026-10-19")], "next_end_date": "2026-07-20"},
         "2026-07-20": {"data": [row("2026-07-17"), {**row("2026-07-20"), "series": "BE"}], "next_end_date": "2026-04-19"},
         "2026-04-19": {"data": [], "next_end_date": None}}


def test_call_retries_lost_sessions(monkeypatch):
    fake = FakeNse(PAGES, fail=2)
    monkeypatch.setattr(nse, "_post", fake)
    assert nse.call("get_stock_history", {"symbol": "SBIN", "months": 3}, pause=0)["data"][0]["date"] == "2026-10-16"
    assert len(fake.tool_calls) == 3


def test_call_gives_up_with_the_last_error(monkeypatch):
    monkeypatch.setattr(nse, "_post", FakeNse(PAGES, fail=99))
    with pytest.raises(nse.NseError, match="Session not found"):
        nse.call("get_stock_history", {"symbol": "SBIN"}, attempts=3, pause=0)


def test_stock_history_pages_back_keeps_eq_and_sorts(monkeypatch):
    fake = FakeNse(PAGES)
    monkeypatch.setattr(nse, "_post", fake)
    out = nse.stock_history("SBIN", bars=3, pause=0)
    assert [r["date"] for r in out] == ["2026-07-17", "2026-10-16", "2026-10-19"]  # the BE-series row is dropped
    assert set(out[0]) == {"date", "open", "high", "low", "close", "volume"}
    assert [c["arguments"].get("endDate") for c in fake.tool_calls] == [None, "2026-07-20"]  # stopped once it had 3 bars


def test_message_reads_plain_json_and_events():
    assert nse._message('{"result": 1}') == {"result": 1}
    assert nse._message("event:message\ndata:{\"result\": 2}\n") == {"result": 2}
    assert nse._message("garbage") == {}
