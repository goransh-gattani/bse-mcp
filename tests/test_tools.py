import datetime
import os

import pytest

from bse_mcp import bse, tools
from bse_mcp.tools import ArgError

from . import fixtures as F


def test_quarter_naming():
    assert tools.quarter_label(130) == "Q1 FY27 (Jun-26)"
    assert tools.quarter_label(126) == "Q1 FY26 (Jun-25)"
    assert tools.quarter_label(129) == "Q4 FY26 (Mar-26)"
    assert tools.quarter_id_for("Q1 FY27") == 130
    assert tools.quarter_id_for("q4 fy26") == 129
    assert tools.quarter_id_for("Q3 FY2026") == 128
    assert tools.quarter_id_for("130.00") == 130
    assert tools.label_from_end("30-Jun-26") == "Q1 FY27"
    assert tools.label_from_end("31-Mar-26") == "Q4 FY26"
    assert tools.label_from_end("garbage") is None
    with pytest.raises(ArgError):
        tools.quarter_id_for("sometime")


def test_last_ended_quarter():
    assert tools.last_ended_quarter(datetime.date(2026, 10, 19)) == 131
    assert tools.last_ended_quarter(datetime.date(2026, 7, 1)) == 130
    assert tools.last_ended_quarter(datetime.date(2026, 6, 30)) == 129


def test_unwrap_double_encoded_json():
    assert bse.unwrap('{"a": "[1, 2]"}') == {"a": [1, 2]}
    assert bse.unwrap("plain") == "plain"
    assert bse.unwrap(["{bad"]) == ["{bad"]


def test_search_scrips(fake):
    out = tools.search_scrips("abb")
    assert len(out) == 3
    assert out[0] == {"scripcode": "500002", "symbol": "ABB", "name": "ABB India Ltd", "isin": "INE117A01022", "market": "in Equity T+1"}


def test_get_quote(fake):
    q = tools.get_quote("500002")
    assert q["name"] == "ABB India Ltd" and q["isin"] == "INE117A01022"
    assert q["price"]["ltp"] == 6963.0 and q["price"]["change_pct"] == 2.76
    assert q["trading"]["delivery_pct"] == 64.27 and q["trading"]["market_cap_cr"] == 147551.8
    assert q["ratios"]["standalone"]["PE"] == 49.38 and q["classification"]["Group"] == "A"
    assert q["range"]["price_band"] == ["6,098.65", "7,453.85"]


def test_bad_scripcode_says_what_to_do(fake):
    with pytest.raises(ArgError, match="search_scrips"):
        tools.get_quote("abb")


def test_market_depth_and_peers(fake):
    d = tools.get_market_depth("500002")
    assert len(d["bids"]) == 5 and d["bids"][0] == {"price": 6962.5, "qty": 26.0} and d["total_bid_qty"] == 9390
    p = tools.get_peers("500002")
    assert len(p) == 4 and any("Hitachi" in (r["Name"] or "") for r in p)


def test_financials_detects_latest_and_skips_unfiled(fake):
    fin = tools.get_financials("500002", quarters=5)
    assert [x["quarter"] for x in fin["quarters"]] == ["Q1 FY27", "Q4 FY26", "Q3 FY26", "Q2 FY26", "Q1 FY26"]
    assert fin["quarters"][0]["period"] == "Apr–Jun 2026"
    probes = [q["Qtr"] for q in fake.sent("Corp_detailedResult_Transpose_ng")]
    assert probes[:2] == ["131.00", "130.00"], "probes one quarter ahead of the results link first"
    assert all(q["lines"] for q in fin["quarters"]), "BSE's empty placeholder for unfiled 131.00 must not appear as a quarter"
    q1 = fin["quarters"][0]
    assert q1["period_end"] == "30-Jun-26" and q1["lines"]["Net Sales/Revenue From Operations"] == 35588.7
    assert q1["derived"] == {"ebitda": 4470.4, "ebitda_margin": 0.1256, "pbt_margin": 0.1401, "tax_rate": 0.258, "pat_margin": 0.104}


def test_financials_upto_by_name(fake):
    fin = tools.get_financials("500002", quarters=1, upto="Q4 FY26")
    assert [x["quarter"] for x in fin["quarters"]] == ["Q4 FY26"]


def test_announcements(fake):
    a = tools.get_announcements("500002", months=6)
    assert a["total"] == 7 and len(a["announcements"]) == 3
    assert a["announcements"][0]["pdf_url"].endswith("/AttachHis/w1.pdf") and a["announcements"][2]["pdf_url"] is None
    head = a["announcements"][0]["headline"]
    assert "<" not in head and "Closure of Trading Window" in head
    sent = fake.sent("AnnSubCategoryGetData")[-1]
    assert (sent["strPrevDate"], sent["strToDate"], sent["strCat"]) == ("20260419", "20261019", "-1")
    assert tools.get_announcements("500002", category="results")["total"] == 2
    tools.get_announcements("500002", months=36)
    assert fake.sent("AnnSubCategoryGetData")[-1]["strPrevDate"] == "20251019", "clamped to 12 months"
    with pytest.raises(ArgError):
        tools.get_announcements("500002", category="everything")


def test_download_pdf(fake, tmp_path):
    path = tools.download_announcement_pdf("w1.pdf", str(tmp_path), "ABB India Ltd_2026-10-10")
    assert os.path.basename(path) == "ABB India Ltd_2026-10-10.pdf"
    assert open(path, "rb").read().startswith(b"%PDF")
    with pytest.raises(ArgError):
        tools.download_announcement_pdf("../etc/passwd", str(tmp_path))


def test_list_scrips(fake):
    out = tools.list_scrips(name_contains="abb")
    assert out["total"] == 2 and out["rows"][0]["SCRIP_CD"] == "500002"
    assert tools.list_scrips(name_contains="abb", limit=1)["returned"] == 1
    with pytest.raises(ArgError):
        tools.list_scrips(segment="Bogus")


def test_call_bse_api(fake):
    raw = tools.call_bse_api("Corp_detailedResult_Transpose_ng", scripcode="500002", quarter="Q1 FY27")
    assert len(raw["table1"]) > 20 and fake.calls[-1][1] == {"Scrip_cd": "500002", "Qtr": "130.00"}
    assert "DeliverableQty" in tools.call_bse_api("SecurityPosition", scripcode="500002")
    with pytest.raises(ArgError):
        tools.call_bse_api("nope")


def test_403_raises_with_remedy(fake):
    fake.refuse.add("getScripHeaderData")
    with pytest.raises(bse.BseError, match="refused.*403"):
        tools.get_quote("500002")


def test_price_history_from_the_12_month_chart(fake, monkeypatch):
    h = tools.get_price_history("500002")
    assert fake.sent("StockReachGraphCas")[0]["flag"] == "12M"
    assert h["bars"] == 250 and h["from"] == "2025-10-21" and h["dates"][1] == "2025-10-22" and h["to"] == h["dates"][-1]
    assert h["closes"][0] == 5000.0 and h["volumes"][0] == 2000.0 and h["symbol"] == "ABB"
    bad = dict(F.HIST_12M, Data=__import__("json").dumps([{"dttm": "yesterday", "vale1": "1.0"}]))
    monkeypatch.setattr(F, "HIST_12M", bad)
    with pytest.raises(bse.BseError, match="unexpected price-history row"):
        tools.get_price_history("500002")


def test_analyze_prices_by_scripcode(fake):
    t = tools.analyze_prices(scripcode="500002")
    assert t["count"] == 250 and t["from"] == "2025-10-21" and "BSE's daily closes" in t["source"]
    assert t["sma"]["sma_200"] is not None and "ohlc_indicators" in t and "price_jumps" not in t and t["volume"]["avg_20"] > 0
    assert len(t["swings"]["lows"]) == 5 and all(0 < p["rsi"] < 100 for p in t["swings"]["lows"] + t["swings"]["highs"])
    w = tools.analyze_prices(scripcode="500002", timeframe="weekly")
    assert w["timeframe"] == "weekly" and 50 <= w["count"] <= 53
    with pytest.raises(ArgError, match="not both"):
        tools.analyze_prices([1.0, 2.0], scripcode="500002")
    with pytest.raises(ArgError, match="scripcode"):
        tools.analyze_prices()
