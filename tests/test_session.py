"""Is a price from today's session? BSE quotes every scrip at all times, so the answer comes from the price's own stamp."""
from datetime import datetime

import pytest

from bse_mcp import bse, tools
from bse_mcp.tools import IST, parse_as_of, session_status

MON_NOON = datetime(2026, 10, 19, 12, 0, tzinfo=IST)


def at(day, hour, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=IST)


def test_parse_as_of():
    assert parse_as_of("21 Oct 26 | 13:23") == at(21, 13, 23)
    assert parse_as_of("07 Sep 06 | 11:38").year == 2006
    assert parse_as_of("19 Oct 2026") is None and parse_as_of(None) is None and parse_as_of("") is None


@pytest.mark.parametrize("now, status", [
    (at(19, 9, 5), "pre_open"),
    (at(19, 12), "live"),
    (at(19, 15, 29), "live"),
    (at(19, 15, 30), "closed_after_session"),
    (at(19, 18), "closed_after_session"),
])
def test_priced_today_is_phased_by_the_clock(now, status):
    assert session_status("19 Oct 26 | 09:07", [], now)["status"] == status


def test_stale_stock_with_a_reference_that_traded_is_not_trading():
    r = session_status("22 Jun 23 | 16:00", ["19 Oct 26 | 11:59"], MON_NOON)
    assert r["status"] == "stock_not_trading" and "2023-06-22" in r["note"]


def test_stale_everything_is_a_closed_market():
    r = session_status("16 Oct 26 | 16:00", ["16 Oct 26 | 15:59", "16 Oct 26 | 16:00"], MON_NOON)
    assert r["status"] == "market_closed" and "2026-10-16" in r["note"]


def test_saturday_morning_is_closed_but_monday_morning_is_only_awaiting_open():
    stale = ["16 Oct 26 | 16:00"]
    assert session_status("16 Oct 26 | 16:00", stale, at(17, 8))["status"] == "market_closed"  # 17 Oct 2026 is a Saturday
    assert session_status("16 Oct 26 | 16:00", stale, at(19, 8))["status"] == "awaiting_open"  # Monday: could still be a holiday


def test_unreadable_stamps_are_unknown_not_guessed():
    assert session_status("yesterday", [], MON_NOON)["status"] == "unknown"
    r = session_status("16 Oct 26 | 16:00", [None, None], MON_NOON)
    assert r["status"] == "unknown" and "unknown" in r["note"]


def header(stamp):
    return {"Header": {"Ason": stamp, "LTP": "100.00"}, "CurrRate": {}, "Cmpname": {}}


@pytest.fixture
def stamps(fake, monkeypatch):
    """Answer getScripHeaderData per scrip from a dict of stamps; other endpoints from the usual fixtures."""
    table, real = {}, bse.get

    def get(name, params):
        if name == "getScripHeaderData":
            if params["scripcode"] not in table:
                raise bse.BseError("no such scrip")
            return header(table[params["scripcode"]])
        return real(name, params)

    monkeypatch.setattr(bse, "get", get)
    return table


def test_tool_fresh_stock_needs_no_reference_calls(stamps):
    stamps["500002"] = "19 Oct 26 | 11:58"  # references deliberately absent: fetching one would raise
    r = tools.get_session_status("500002")
    assert r["status"] == "live" and r["scripcode"] == "500002" and r["data_as_of"] == "2026-10-19T11:58+05:30"


def test_tool_suspended_scrip_while_the_market_trades(stamps):
    stamps.update({"500102": "22 Jun 23 | 16:00", "500325": "19 Oct 26 | 11:59"})
    assert tools.get_session_status("500102")["status"] == "stock_not_trading"


def test_tool_holiday_when_every_reference_is_stale(stamps):
    stamps.update({"500002": "16 Oct 26 | 16:00", "500325": "16 Oct 26 | 16:00", "500180": "16 Oct 26 | 16:00"})
    assert tools.get_session_status("500002")["status"] == "market_closed"


def test_tool_reference_failure_does_not_fail_the_tool(stamps):
    stamps["500002"] = "16 Oct 26 | 16:00"  # both references raise BseError
    assert tools.get_session_status("500002")["status"] == "unknown"


def test_a_reference_scrip_is_not_its_own_proof(stamps):
    stamps.update({"500325": "16 Oct 26 | 16:00", "500180": "16 Oct 26 | 16:00"})
    assert tools.get_session_status("500325")["status"] == "market_closed"


def test_quote_and_analyses_carry_the_session(fake):
    # fixtures stamp the quote 12 Oct while the pinned clock is 19 Oct, so nothing traded "today"
    assert tools.get_quote("500002")["session"]["status"] == "market_closed"
    assert tools.analyze_fundamentals("500002")["session"]["status"] == "market_closed"
    assert tools.analyze_prices(scripcode="500002")["session"]["status"] == "market_closed"
    assert "session" not in tools.analyze_prices(closes=[100.0 + i for i in range(30)])
