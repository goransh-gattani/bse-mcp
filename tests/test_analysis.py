"""Formulas checked against independent references, and the fundamentals pipeline on recorded BSE data."""
import math

import pytest

from bse_mcp import analysis as A, tools
from bse_mcp.tools import ArgError

# StockCharts' published RSI worked example (closes to 4 dp, expected RSI after 15..20 closes).
RSI_CLOSES = [44.3389, 44.0902, 44.1497, 43.6124, 44.2779, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
              45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]
RSI_EXPECTED = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97]


def test_rsi_matches_published_example():
    assert [round(A.rsi(RSI_CLOSES[:k]), 2) for k in range(15, 21)] == RSI_EXPECTED
    assert A.rsi(RSI_CLOSES[:14]) is None


def test_ema_and_macd_exact_on_a_straight_line():
    # For x_t = t, an SMA-seeded EMA(n) equals t - (n-1)/2 exactly, so MACD(12,26) = 12.5 - 5.5 = 7 and signal = 7.
    line = [float(i) for i in range(1, 251)]  # 250 closes, enough for SMA200
    assert A.ema_series(line, 12)[-1] == pytest.approx(250 - 5.5)
    assert A.ema_series(line, 26)[-1] == pytest.approx(250 - 12.5)
    t = A.technicals(line)
    assert t["macd"]["macd"] == pytest.approx(7.0) and t["macd"]["signal"] == pytest.approx(7.0) and abs(t["macd"]["histogram"]) < 1e-9
    assert t["rsi_14"] == 100.0 and t["trend"]["state"].startswith("golden")


def test_bollinger_uses_population_sd():
    w = [float(i) for i in range(1, 21)]
    b = A.technicals(w)["bollinger_20_2"]
    sd = math.sqrt((20 ** 2 - 1) / 12)  # population SD of 1..20
    assert b["middle"] == 10.5 and b["upper"] == pytest.approx(10.5 + 2 * sd, abs=0.01) and b["lower"] == pytest.approx(10.5 - 2 * sd, abs=0.01)


def test_drawdown_returns_volatility():
    assert A.max_drawdown([100, 120, 90, 130], ["d0", "d1", "d2", "d3"]) == {"drawdown": -0.25, "peak": "d1", "trough": "d2"}
    flat = A.technicals([100.0] * 300)
    assert flat["volatility_annualised"] == 0 and flat["max_drawdown"]["drawdown"] == 0.0 and flat["returns"]["1y"] == 0
    # alternating +r/-r log returns: sample SD known in closed form
    r = 0.01
    xs = [100 * math.exp(r * (i % 2)) for i in range(253)]
    n = 252
    mean = (r * (n // 2) - r * (n // 2)) / n
    expected = math.sqrt(sum(((r if i % 2 == 0 else -r) - mean) ** 2 for i in range(n)) / (n - 1)) * math.sqrt(252)
    assert A.technicals(xs)["volatility_annualised"] == pytest.approx(expected, abs=1e-4)


def test_returns_windows_and_cagr_with_dates():
    xs = [100.0 * (1.1 ** (i / 252)) for i in range(253)]  # +10% over 252 trading days
    t = A.technicals(xs)
    assert t["returns"]["1y"] == pytest.approx(0.10, abs=1e-4) and "3y" not in t["returns"]
    t2 = A.technicals([100.0, 121.0], ["2024-01-01", "2026-01-01"])
    assert t2["cagr"] == pytest.approx(0.0998, abs=1e-3)  # two years at ~10%/yr


def test_bad_price_input_is_rejected():
    with pytest.raises(ArgError, match="oldest first"):
        tools.analyze_prices([1, 2, 3], ["2026-01-03", "2026-01-02", "2026-01-01"])
    with pytest.raises(ArgError, match="positive"):
        tools.analyze_prices([1, -2, 3])
    with pytest.raises(ArgError, match="differ in length"):
        tools.analyze_prices([1, 2, 3], ["2026-01-01"])
    assert "needs_more_data" in tools.analyze_prices([1.0, 2.0, 3.0])


def test_period_labels():
    assert tools.period_label("01-Apr-26", "30-Jun-26") == "Apr–Jun 2026"
    assert tools.period_label("01-Dec-25", "28-Feb-26") == "Dec 2025–Feb 2026"
    assert tools.period_label("", "") is None


def test_unit_detection():
    card = {"col2": "Jun-26", "col3": "Mar-26", "resultinCr": [{"title": "Revenue", "v1": "3,558.87", "v2": "3,184.06"}]}
    assert A.unit_factor(35588.7, card, "30-Jun-26")["unit"] == "Rs million"
    assert A.unit_factor(355887.0, card, "30-Jun-26")["unit"] == "Rs lakh"
    assert A.unit_factor(3558.87, card, "30-Jun-26")["unit"] == "Rs crore"
    assert A.unit_factor(31840.6, card, "31-Mar-26")["unit"] == "Rs million"   # matched via col3
    assert A.unit_factor(12345.0, card, "30-Jun-26")["crore_per_unit"] is None  # no known unit: skip Rs-crore figures
    assert A.unit_factor(35588.7, None, "30-Jun-26")["basis"].startswith("assumed")


def test_analyze_fundamentals_on_recorded_abb(fake):
    a = tools.analyze_fundamentals("500002", quarters=8)
    assert [q["period"] for q in a["quarters"]] == ["Apr–Jun 2026", "Jan–Mar 2026", "Oct–Dec 2025", "Jul–Sep 2025", "Apr–Jun 2025"]
    latest = a["quarters"][0]
    m = latest["metrics"]
    assert (m["ebitda"], m["ebitda_margin"], m["interest_coverage"], m["other_income_share_of_pbt"]) == (4470.4, 0.1256, 292.68, 0.1858)
    assert m["cost_structure"] == {"materials": 0.5961, "employee": 0.0705, "other_expenses": 0.2078, "depreciation": 0.011}
    assert latest["yoy"] == {"revenue": 0.1207, "ebitda": 0.0796, "pbt": 0.052, "pat": 0.0511, "eps": 0.0505, "ebitda_margin_change_pts": -0.48}
    assert latest["qoq"]["revenue"] == 0.1177
    assert a["quarters"][-1]["yoy"] is None, "no quarter a year before the oldest one"
    ttm = a["ttm"]
    assert ttm["available"] and ttm["revenue"] == 136106.6 and ttm["eps"] == 73.4 and ttm["growth_vs_prior_ttm"] is None
    v = a["valuation"]
    assert a["unit"]["unit"] == "Rs million" and v["ttm_revenue_cr"] == 13610.66
    assert v["pe_ttm"] == round(6963.0 / 73.4, 2) and v["price_to_sales_ttm"] == round(147551.8 / 13610.66, 2)
    assert v["bse_reported"]["pe"] == 49.38


def test_ttm_needs_four_consecutive_quarters(fake):
    a = tools.analyze_fundamentals("500002", quarters=2)
    assert a["ttm"]["available"] is False and "4 consecutive" in a["ttm"]["reason"]
    assert a["valuation"]["available"] is False
