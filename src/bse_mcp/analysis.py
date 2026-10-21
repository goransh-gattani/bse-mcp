"""Financial and technical calculations. Pure functions: numbers in, numbers out, no BSE access.

The formulas are the standard textbook ones; each output says what it is in `definitions`, so
Claude reports computed figures instead of doing arithmetic over filings itself.
"""

from __future__ import annotations

import math
import re
import statistics
from datetime import date, datetime

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _r(x, nd=4):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, nd)


def _ratio(a, b):
    """a / b, or None when either is missing or b is zero."""
    return a / b if a is not None and b not in (None, 0) else None


def _growth(now, before):
    """Fractional change. None on a missing or non-positive base: growth off a loss isn't meaningful."""
    return now / before - 1 if now is not None and before is not None and before > 0 else None


# ======================================================================= fundamentals
# BSE's line names in Corp_detailedResult_Transpose_ng (expenses are negative there).
L = {"sales": "Net Sales/Revenue From Operations", "other_income": "Other Income", "cmc": "Cost of Materials Consumed",
     "purch": "Purchases of stock-in-trade", "inv": "Changes in inventories of finished goods, work-in-progress and stock-in-trade",
     "emp": "Employee benefit expense", "oth": "Other Expenses", "dep": "Depreciation and amortisation expense", "fin": "Finance Costs",
     "pbt": "Profit (+)/ Loss (-) from Ordinary Activities before Tax", "tax": "Tax",
     "pat": "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax", "net": "Net Profit", "eps": "Basic EPS for continuing operation"}

FUNDAMENTAL_DEFINITIONS = {
    "ebitda": "revenue + materials + stock-in-trade purchases + inventory change + employee cost + other expenses (operating profit before depreciation, interest, other income and tax)",
    "ebit": "PBT + finance costs (includes other income)",
    "interest_coverage": "EBIT / finance costs",
    "pat": "profit after tax from continuing operations",
    "net_profit": "reported net profit, including discontinued operations and other items",
    "eps": "basic EPS from continuing operations (Rs per share)",
    "tax_rate": "tax / PBT",
    "other_income_share_of_pbt": "other income / PBT: how much of profit comes from outside operations",
    "cost_structure": "each cost as a share of revenue; materials = materials consumed + stock-in-trade purchases + inventory change",
    "yoy": "change against the quarter ending 12 months earlier; qoq: against the quarter ending 3 months earlier. None when that quarter is missing or the base is zero or negative",
    "ttm": "sum of the latest 4 consecutive quarters (trailing twelve months); margins are TTM sums divided by TTM revenue",
    "pe_ttm": "share price / TTM EPS (continuing operations)",
    "price_to_sales_ttm": "market capitalisation / TTM revenue",
}


def quarter_metrics(lines: dict) -> dict:
    g = lambda k: lines.get(L[k])  # noqa: E731
    sales = g("sales")
    op_costs = [g(k) for k in ("cmc", "purch", "inv", "emp", "oth")]
    ebitda = sales + sum(op_costs) if sales is not None and all(c is not None for c in op_costs) else None
    fin = -g("fin") if g("fin") is not None else None  # finance costs as a positive number
    pbt, tax = g("pbt"), g("tax")
    ebit = pbt + fin if pbt is not None and fin is not None else None
    materials = sum(g(k) for k in ("cmc", "purch", "inv")) if all(g(k) is not None for k in ("cmc", "purch", "inv")) else None
    share = lambda v: _r(_ratio(-v, sales)) if v is not None else None  # noqa: E731  (costs are negative)
    return {
        "revenue": sales, "other_income": g("other_income"), "ebitda": _r(ebitda, 2), "ebit": _r(ebit, 2), "pbt": pbt,
        "pat": g("pat"), "net_profit": g("net"), "eps": g("eps"), "finance_costs": fin, "depreciation": -g("dep") if g("dep") is not None else None,
        "ebitda_margin": _r(_ratio(ebitda, sales)), "pbt_margin": _r(_ratio(pbt, sales)), "pat_margin": _r(_ratio(g("pat"), sales)),
        "tax_rate": _r(_ratio(-tax if tax is not None else None, pbt)),
        "interest_coverage": _r(_ratio(ebit, fin), 2) if fin else None,
        "other_income_share_of_pbt": _r(_ratio(g("other_income"), pbt)),
        "cost_structure": {"materials": share(materials), "employee": share(g("emp")), "other_expenses": share(g("oth")), "depreciation": share(g("dep"))},
    }


def _month_index(period_end: str) -> int | None:
    m = re.fullmatch(r"\d+-(\w{3})-(\d{2})", period_end or "")
    return (2000 + int(m.group(2))) * 12 + MONTHS.index(m.group(1)) if m and m.group(1) in MONTHS else None


GROWTH_KEYS = ("revenue", "ebitda", "pbt", "pat", "eps")


def fundamentals(quarters: list[dict]) -> dict:
    """quarters: get_financials()['quarters'] (newest first). Adds metrics, YoY/QoQ growth and TTM."""
    rows = []
    for q in quarters:
        mi = _month_index(q.get("period_end"))
        if mi is None:
            continue
        rows.append({"quarter": q.get("quarter"), "period": q.get("period"), "period_end": q["period_end"], "_m": mi,
                     "metrics": quarter_metrics(q.get("lines") or {})})
    by_m = {r["_m"]: r for r in rows}
    for r in rows:
        for label, back in (("yoy", 12), ("qoq", 3)):
            prev = by_m.get(r["_m"] - back)
            r[label] = {k: _r(_growth(r["metrics"][k], prev["metrics"][k])) for k in GROWTH_KEYS} if prev else None
            if prev:
                r[label]["ebitda_margin_change_pts"] = _r(_pts(r["metrics"]["ebitda_margin"], prev["metrics"]["ebitda_margin"]), 2)
    out = {"quarters": [{k: v for k, v in r.items() if k != "_m"} for r in rows]}
    out["ttm"] = _ttm(by_m, rows[0]["_m"]) if rows else {"available": False, "reason": "no quarters"}
    if out["ttm"].get("available"):
        prior = _ttm(by_m, rows[0]["_m"] - 12)
        out["ttm"]["growth_vs_prior_ttm"] = ({k: _r(_growth(out["ttm"][k], prior[k])) for k in GROWTH_KEYS} if prior.get("available")
                                             else None)
    return out


def _pts(a, b):
    return (a - b) * 100 if a is not None and b is not None else None


def _ttm(by_m: dict, latest_m: int) -> dict:
    window = [by_m.get(latest_m - 3 * i) for i in range(4)]
    if any(w is None for w in window):
        missing = [MONTHS[(latest_m - 3 * i) % 12] + "-" + str((latest_m - 3 * i) // 12)[-2:] for i, w in enumerate(window) if w is None]
        return {"available": False, "reason": f"needs 4 consecutive quarters; missing quarter(s) ending {', '.join(missing)} (ask for more quarters)"}
    t = {}
    for k in ("revenue", "ebitda", "pbt", "pat", "net_profit", "eps", "other_income"):
        vals = [w["metrics"][k] for w in window]
        t[k] = _r(sum(vals), 2) if all(v is not None for v in vals) else None
    t.update({"available": True, "quarters": [w["period"] or w["quarter"] for w in window],
              "ebitda_margin": _r(_ratio(t["ebitda"], t["revenue"])), "pat_margin": _r(_ratio(t["pat"], t["revenue"]))})
    return t


def unit_factor(latest_revenue: float | None, results_card: dict | None, latest_end: str | None) -> dict:
    """Rs crore per unit of the filed figures, read off BSE's own Rs-crore results card for the same quarter.

    BSE labels the detailed figures Rs million, but a company can file in lakhs or crores; comparing the
    same quarter's revenue in both places tells us which, instead of assuming."""
    known = {0.1: "Rs million", 0.01: "Rs lakh", 1.0: "Rs crore", 0.0001: "Rs thousand"}
    card_cr = None
    if isinstance(results_card, dict) and latest_end:
        m = re.fullmatch(r"\d+-(\w{3})-(\d{2})", latest_end)
        want = f"{m.group(1)}-{m.group(2)}" if m else None
        col = next((c for c in ("col2", "col3") if results_card.get(c) == want), None)
        row = next((r for r in results_card.get("resultinCr") or [] if str(r.get("title", "")).lower().startswith("revenue")), None)
        if col and row:
            card_cr = _num({"col2": row.get("v1"), "col3": row.get("v2")}[col])
    if card_cr and latest_revenue:
        f = card_cr / latest_revenue
        for k, name in known.items():
            if abs(f / k - 1) < 0.02:
                return {"crore_per_unit": k, "unit": name, "basis": "matched against BSE's Rs-crore results card"}
        return {"crore_per_unit": None, "unit": None, "basis": f"filed figures don't match BSE's Rs-crore card by a known unit (ratio {f:.6g}); Rs-crore values skipped"}
    return {"crore_per_unit": 0.1, "unit": "Rs million", "basis": "assumed (BSE's label); couldn't cross-check against the Rs-crore card"}


def _num(v):
    try:
        return float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None


def valuation(ttm: dict, price: float | None, market_cap_cr: float | None, crore_per_unit: float | None) -> dict:
    if not ttm.get("available"):
        return {"available": False, "reason": "needs TTM figures: " + ttm.get("reason", "")}
    rev_cr = ttm["revenue"] * crore_per_unit if crore_per_unit and ttm.get("revenue") is not None else None
    eps = ttm.get("eps")
    return {"available": True, "price": price, "market_cap_cr": market_cap_cr, "ttm_revenue_cr": _r(rev_cr, 2), "ttm_eps": eps,
            "pe_ttm": _r(_ratio(price, eps), 2) if eps and eps > 0 else None,
            "price_to_sales_ttm": _r(_ratio(market_cap_cr, rev_cr), 2),
            "not_computed": "EV/EBITDA, P/B, ROCE and debt ratios need the balance sheet, which BSE's results endpoints don't give"}


# ======================================================================= technicals
TECHNICAL_DEFINITIONS = {
    "returns": "close-to-close change over the last N trading days (1w=5, 1m=21, 3m=63, 6m=126, 1y=252, 3y=756, 5y=1260)",
    "cagr": "compound annual growth from the first to the last close (calendar days when dates are given, else 252 trading days a year)",
    "volatility_annualised": "sample standard deviation of daily log returns over the last 252 days (or all, if fewer) x sqrt(252)",
    "max_drawdown": "largest peak-to-trough fall in the closes",
    "sma": "simple moving average of the last N closes",
    "ema": "exponential moving average, weight 2/(N+1), seeded with the SMA of the first N closes",
    "macd": "EMA12 - EMA26; signal = EMA9 of MACD; histogram = MACD - signal",
    "rsi_14": "Wilder's RSI: 100 - 100/(1 + average gain / average loss), Wilder-smoothed over 14 periods",
    "bollinger_20_2": "SMA20 +/- 2 population standard deviations of the last 20 closes; percent_b = (close - lower)/(upper - lower)",
    "range_52w": "high and low of the last 252 closes (closing prices only, so intraday extremes are not included)",
    "trend": "SMA50 against SMA200: 'golden cross' state when above, 'death cross' state when below",
}
WINDOWS = {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260}


def sma(xs: list[float], n: int) -> float | None:
    return sum(xs[-n:]) / n if len(xs) >= n else None


def ema_series(xs: list[float], n: int) -> list[float]:
    """EMA values from index n-1 onward (seeded with the SMA of the first n)."""
    if len(xs) < n:
        return []
    a = 2 / (n + 1)
    out = [sum(xs[:n]) / n]
    for x in xs[n:]:
        out.append(a * x + (1 - a) * out[-1])
    return out


def rsi(xs: list[float], n: int = 14) -> float | None:
    if len(xs) < n + 1:
        return None
    ch = [b - a for a, b in zip(xs, xs[1:])]
    gain = sum(max(c, 0) for c in ch[:n]) / n
    loss = sum(max(-c, 0) for c in ch[:n]) / n
    for c in ch[n:]:
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
    if loss == 0:
        return 100.0 if gain > 0 else 50.0
    return 100 - 100 / (1 + gain / loss)


def max_drawdown(xs: list[float], dates: list[str] | None = None) -> dict:
    peak_i, worst, at = 0, 0.0, (0, 0)
    for i, x in enumerate(xs):
        if x > xs[peak_i]:
            peak_i = i
        dd = x / xs[peak_i] - 1
        if dd < worst:
            worst, at = dd, (peak_i, i)
    d = (lambda i: dates[i] if dates else i)  # noqa: E731
    return {"drawdown": _r(worst), "peak": d(at[0]), "trough": d(at[1])} if worst < 0 else {"drawdown": 0.0, "peak": None, "trough": None}


def _parse_date(s: str) -> date:
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%Y%m%d"):
        try:
            return datetime.strptime(s[:11].strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"unrecognised date {s!r}; use YYYY-MM-DD")


def technicals(closes: list[float], dates: list[str] | None = None) -> dict:
    """Indicators on daily closes, oldest first. Raises ValueError on input that can't be right."""
    xs = [float(c) for c in closes]
    if len(xs) < 2:
        raise ValueError("need at least 2 closes")
    if any(not math.isfinite(x) or x <= 0 for x in xs):
        raise ValueError("closes must be positive numbers")
    if dates is not None:
        if len(dates) != len(xs):
            raise ValueError(f"dates ({len(dates)}) and closes ({len(xs)}) differ in length")
        parsed = [_parse_date(str(d)) for d in dates]
        if any(b <= a for a, b in zip(parsed, parsed[1:])):
            raise ValueError("dates must be strictly increasing: pass the series oldest first")
    last = xs[-1]
    rets = {k: _r(last / xs[-1 - n] - 1) for k, n in WINDOWS.items() if len(xs) > n}
    if dates is not None:
        days = (parsed[-1] - parsed[0]).days
        years = days / 365.25
    else:
        years = (len(xs) - 1) / 252
    cagr = _r((last / xs[0]) ** (1 / years) - 1) if years >= 1 else None
    logr = [math.log(b / a) for a, b in zip(xs, xs[1:])][-252:]
    vol = _r(statistics.stdev(logr) * math.sqrt(252)) if len(logr) >= 2 else None
    e12, e26 = ema_series(xs, 12), ema_series(xs, 26)
    macd = None
    if e26:
        line = [a - b for a, b in zip(e12[len(e12) - len(e26):], e26)]
        sig = ema_series(line, 9)
        if sig:
            macd = {"macd": _r(line[-1], 4), "signal": _r(sig[-1], 4), "histogram": _r(line[-1] - sig[-1], 4)}
    boll = None
    if len(xs) >= 20:
        w = xs[-20:]
        mid, sd = sum(w) / 20, statistics.pstdev(w)
        up, lo = mid + 2 * sd, mid - 2 * sd
        boll = {"middle": _r(mid, 2), "upper": _r(up, 2), "lower": _r(lo, 2),
                "percent_b": _r((last - lo) / (up - lo)) if up > lo else None, "bandwidth": _r((up - lo) / mid)}
    yr = xs[-252:]
    hi, lo52 = max(yr), min(yr)
    s50, s200 = sma(xs, 50), sma(xs, 200)
    out = {
        "count": len(xs), "from": dates[0] if dates else None, "to": dates[-1] if dates else None, "last_close": last,
        "returns": rets, "cagr": cagr, "volatility_annualised": vol, "max_drawdown": max_drawdown(xs, dates),
        "max_drawdown_1y": max_drawdown(xs[-252:], dates[-252:] if dates else None),
        "sma": {f"sma_{n}": _r(sma(xs, n), 2) for n in (20, 50, 200)},
        "price_vs_sma": {f"vs_sma_{n}": _r(_ratio(last, sma(xs, n)) - 1) if sma(xs, n) else None for n in (20, 50, 200)},
        "ema": {"ema_12": _r(e12[-1], 2) if e12 else None, "ema_26": _r(e26[-1], 2) if e26 else None},
        "macd": macd, "rsi_14": _r(rsi(xs), 2), "bollinger_20_2": boll,
        "range_52w": {"high": hi, "low": lo52, "position": _r((last - lo52) / (hi - lo52)) if hi > lo52 else None,
                      "below_high": _r(last / hi - 1), "window_days": len(yr)},
        "trend": ({"sma50_vs_sma200": _r(s50 / s200 - 1), "state": "golden cross (SMA50 above SMA200)" if s50 > s200 else "death cross (SMA50 below SMA200)"}
                  if s50 and s200 else None),
    }
    missing = [name for name, need in (("sma_200 / trend", 200), ("1y range and volatility", 252), ("macd", 34), ("rsi_14", 15), ("bollinger", 20)) if len(xs) < need]
    if missing:
        out["needs_more_data"] = f"{len(xs)} closes given; for {', '.join(missing)} pass more history (~260 trading days covers everything except 3y/5y returns)"
    return out
