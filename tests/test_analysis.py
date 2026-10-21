"""Formulas checked against independent references, and the fundamentals pipeline on recorded BSE data."""
import math
from datetime import date, timedelta

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
    assert t["ema"]["ema_50"] == 250 - 24.5


def test_price_jumps_flag_possible_unadjusted_splits():
    dates = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(40)]
    t = A.technicals([100.0] * 20 + [50.0] * 20, dates)  # a 1:1 bonus or 2-for-1 split, unadjusted
    assert t["price_jumps"]["bars"] == [{"at": dates[20], "change": -0.5}] and "split or bonus" in t["price_jumps"]["note"]
    assert A.technicals([100.0] * 20 + [50.0] * 20, dates, timeframe="weekly")["price_jumps"]["bars"][0]["at"] == dates[20]
    assert "price_jumps" not in A.technicals([float(i) for i in range(101, 251)])


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


# ---- OHLC indicators, each against a value worked out by hand
def _rising(n=60):
    c = [100.0 + i for i in range(n)]
    return [x + 1 for x in c], [x - 1 for x in c], c  # highs, lows, closes


def test_atr_true_range_and_gaps():
    h, l, c = [101.0] * 30, [99.0] * 30, [100.0] * 30
    assert A.atr(h, l, c) == pytest.approx(2.0)
    assert A.true_ranges([101, 111], [99, 109], [100, 110]) == [2, 11]  # gap up: high - previous close


def test_adx_is_100_in_a_perfectly_steady_uptrend():
    h, l, c = _rising()
    d = A.adx(h, l, c)
    assert (d["adx"], d["plus_di"], d["minus_di"]) == (100.0, 50.0, 0.0) and d["strength"] == "trending" and d["direction"].startswith("up")
    assert A.adx(h[:27], l[:27], c[:27]) is None  # needs 2 x 14 bars


def test_stochastic_and_pivots():
    h, l, c = _rising()
    assert A.stochastic(h, l, c) == {"k": round(14 / 15 * 100, 2), "d": round(14 / 15 * 100, 2)}
    t = A.technicals([100.0] * 29 + [105.0], highs=[101.0] * 29 + [110.0], lows=[99.0] * 29 + [100.0])
    assert t["pivots_classic"] == {"P": 105.0, "R1": 110.0, "S1": 100.0, "R2": 115.0, "S2": 95.0, "R3": 120.0, "S3": 90.0}


def test_swings_and_fibonacci():
    s = A.swings([1, 2, 5, 2, 1, 2, 6, 2, 1], [1, 2, 5, 2, 1, 2, 6, 2, 1])
    assert [p["price"] for p in s["highs"]] == [5, 6] and [p["price"] for p in s["lows"]] == [1]
    h = [150.0, 120.0, 100.0, 140.0, 200.0, 180.0]
    f = A.fibonacci(h, h, 180.0)
    assert f["move"] == "up" and f["retracements"]["61.8%"] == 138.2 and f["retracements"]["50%"] == 150.0
    assert f["extensions"]["161.8%"] == 261.8 and f["extensions"]["200%"] == 300.0 and f["retraced_so_far"] == 0.2
    # pullback to 180 after the 200 high: C-based projections = 180 + 100 x ratio
    assert f["pullback"]["price"] == 180.0 and f["pullback"]["projections"] == {"100%": 280.0, "127.2%": 307.2, "161.8%": 341.8, "200%": 380.0}
    down = A.fibonacci([200.0, 150.0, 100.0], [200.0, 150.0, 100.0], 120.0)
    assert down["move"] == "down" and down["retracements"]["38.2%"] == 138.2


def _bullish_divergence_series():
    c = [100.0 + (i % 2) for i in range(20)]
    for _ in range(8):
        c.append(c[-1] - 3)          # fast drop to a first low (77)
    for _ in range(8):
        c.append(c[-1] + 2)
    while c[-1] > 78:
        c += [c[-1] - 3, c[-1] - 1]  # gentle zigzag down
    c.append(c[-1] - 3)              # lower second low (75), with far less selling pressure
    return c + [c[-1] + 3, c[-1] + 6]


def test_rsi_divergence_regular_bullish():
    c = _bullish_divergence_series()
    d = A.rsi_divergence(c, c, c)
    assert len(d) == 1 and d[0]["type"] == "regular bullish"
    (a, b) = d[0]["points"]
    assert b["price"] < a["price"] and b["rsi"] > a["rsi"]
    assert A.rsi_divergence([float(x) for x in range(1, 80)], [float(x) for x in range(1, 80)], [float(x) for x in range(1, 80)]) == []


def test_weekly_resampling():
    days = ["2026-01-05", "2026-01-06", "2026-01-09", "2026-01-12", "2026-01-16", "2026-01-19"]  # Mon..Fri, Mon, Fri, Mon
    w = A.to_weekly(days, [10, 12, 11, 13, 14, 15], [11, 15, 12, 14, 16, 15], [9, 11, 10, 12, 13, 14], [1, 2, 3, 4, 5, 6])
    assert w == {"dates": ["2026-01-09", "2026-01-16", "2026-01-19"], "closes": [11, 14, 15], "highs": [15, 16, 15],
                 "lows": [9, 12, 14], "volumes": [6, 9, 6]}
    t = A.technicals([10.0, 12.0, 11.0, 13.0, 14.0, 15.0], days, timeframe="weekly")
    assert t["timeframe"] == "weekly" and t["count"] == 3 and t["last_close"] == 15.0


def test_ohlc_validation_and_volume():
    with pytest.raises(ValueError, match="together"):
        A.technicals([1.0, 2.0], highs=[1.0, 2.0])
    with pytest.raises(ValueError, match="low <= close <= high"):
        A.technicals([1.0, 2.0], highs=[1.0, 1.5], lows=[0.5, 1.0])
    with pytest.raises(ValueError, match="needs the daily dates"):
        A.technicals([1.0, 2.0], timeframe="weekly")
    t = A.technicals([100.0] * 25, volumes=[1000.0] * 24 + [3000.0])
    assert t["volume"]["last_vs_avg_20"] == round(3000 / 1100, 4)
    assert "ohlc_indicators" in t, "closes only: says what highs/lows would add"


def test_since_entry_trailing_levels():
    days = [f"2026-03-{d:02d}" for d in range(1, 31)]
    c = [100.0 + i for i in range(30)]
    h, l = [x + 1 for x in c], [x - 1 for x in c]
    t = A.technicals(c, days, h, l, entry_date="2026-03-11")
    se = t["since_entry"]
    a14 = A.atr(h, l, c, 14)
    assert se["first_bar"] == "2026-03-11" and se["bars"] == 20 and se["highest_close"] == 129.0 and se["highest_high"] == 130.0
    assert se["atr_trail"]["1.5x"] == round(129 - 1.5 * a14, 2) and se["chandelier_since_entry"] == round(130 - 3 * a14, 2)
    with pytest.raises(ValueError, match="after the last bar"):
        A.technicals(c, days, h, l, entry_date="2026-04-15")
    short = A.technicals(c, days, h, l, entry_date="2026-03-11", side="short")["since_entry"]
    assert short["lowest_close"] == 110.0 and short["atr_trail"]["2x"] == round(110 + 2 * a14, 2)


# SBI's Apr-Jun 2026 filing as BSE returned it on 21 Oct 2026 (Rs million; BSE's signs kept: sub-items and NPA/capital ratios negative).
SBI_Q1FY27 = {"Interest Earned/Net Income from sales/services": 1278964.6, "Income on Investments": -295101.9, "Other Income": 159226.9,
              "Total Income": 1438191.5, "Interest Expended": -809040.2, "Employee Cost": -174238.0, "Other operating expenses": -119621.5,
              "Total Expenditure for Banks": -1102899.7, "Operating Profit Before Provisions and Contingencies": 335291.8,
              "Provisions (other than tax) and Contingencies": -50467.7, "Profit (+)/ Loss (-) from Ordinary Activities before Tax": 284824.1,
              "Tax": -73611.9, "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax": 211212.2, "Net Profit": 211212.2,
              "CET 1 Ratio": -12.89, "Basic EPS before Extraordinary items": 22.88, "Amount of Gross NPA": -742720.6,
              "Amount of Net NPA": -191584.9, "% of Gross NPAs": -1.47, "% of Net NPAs": -0.38, "Return on Assets": 1.11}


def test_bank_metrics_from_a_real_filing():
    assert A.is_bank(SBI_Q1FY27) and not A.is_bank({"Net Sales/Revenue From Operations": 1.0})
    m = A.bank_metrics(SBI_Q1FY27)
    assert m["nii"] == pytest.approx(1278964.6 - 809040.2) and m["provisions"] == 50467.7
    assert m["cost_to_income"] == pytest.approx(round(293859.5 / (469924.4 + 159226.9), 4))
    assert m["gross_npa_pct"] == 1.47 and m["net_npa_pct"] == 0.38 and m["cet1_pct"] == 12.89  # signs fixed
    assert m["npa_coverage"] == pytest.approx(round(1 - 191584.9 / 742720.6, 4)) and m["eps"] == 22.88


def test_fundamentals_switches_to_bank_metrics():
    ends = ["30-Jun-26", "31-Mar-26", "31-Dec-25", "30-Sep-25", "30-Jun-25"]
    qs = [{"quarter": f"q{i}", "period": f"p{i}", "period_end": e,
           "lines": {k: v * (1 - 0.02 * i) if isinstance(v, float) else v for k, v in SBI_Q1FY27.items()}} for i, e in enumerate(ends)]
    out = A.fundamentals(qs)
    assert out["kind"] == "bank" and "ebitda" not in out["quarters"][0]["metrics"]
    assert out["quarters"][0]["yoy"]["nii"] == pytest.approx(round(1 / 0.92 - 1, 4))
    assert "cost_to_income_change_pts" in out["quarters"][0]["qoq"]
    assert out["ttm"]["available"] and out["ttm"]["eps"] == pytest.approx(round(22.88 * (1 + 0.98 + 0.96 + 0.94), 2))
    assert "nii" in A.definitions_for("bank") and "ebitda" not in A.definitions_for("bank")
    assert A.fundamentals([{**qs[0], "lines": {"Net Sales/Revenue From Operations": 10.0}}])["kind"] == "company"
