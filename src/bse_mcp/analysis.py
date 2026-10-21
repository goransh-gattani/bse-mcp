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


# Banks file a different format (Schedule III for banks): interest earned/expended, operating profit before
# provisions, provisions, and asset-quality lines. BSE stores sub-items and the NPA/capital ratios negative.
B = {"int_earned": "Interest Earned/Net Income from sales/services", "int_expended": "Interest Expended", "other_income": "Other Income",
     "emp": "Employee Cost", "oth": "Other operating expenses", "ppop": "Operating Profit Before Provisions and Contingencies",
     "prov": "Provisions (other than tax) and Contingencies", "pbt": L["pbt"], "tax": L["tax"], "pat": L["pat"], "net": L["net"],
     "eps": "Basic EPS before Extraordinary items", "gnpa": "Amount of Gross NPA", "nnpa": "Amount of Net NPA",
     "gnpa_pct": "% of Gross NPAs", "nnpa_pct": "% of Net NPAs", "roa": "Return on Assets", "cet1": "CET 1 Ratio"}

BANK_DEFINITIONS = {
    "revenue": "interest earned, which is what BSE's results card calls a bank's revenue",
    "nii": "net interest income: interest earned - interest expended",
    "ppop": "operating profit before provisions and contingencies, as filed",
    "cost_to_income": "(employee cost + other operating expenses) / (NII + other income)",
    "credit_cost_share_of_ppop": "provisions (other than tax) / PPOP: how much of operating profit went to provisions",
    "non_interest_income_share": "other income / (NII + other income)",
    "gross_npa_pct, net_npa_pct": "as filed, % of advances",
    "npa_coverage": "1 - net NPA / gross NPA (amounts): the share of bad loans already provided for",
    "roa_pct": "return on assets as filed (%, annualised by the bank)",
    "cet1_pct": "common equity tier 1 capital ratio as filed (%)",
    "eps": "basic EPS before extraordinary items (Rs per share)",
    "not_computed": "NIM, CASA, credit growth and P/B need balance-sheet data that BSE's results endpoints don't give",
}


def definitions_for(kind: str) -> dict:
    if kind != "bank":
        return FUNDAMENTAL_DEFINITIONS
    shared = ("tax_rate", "yoy", "ttm", "pe_ttm", "price_to_sales_ttm")
    return {**{k: FUNDAMENTAL_DEFINITIONS[k] for k in shared}, **BANK_DEFINITIONS}


def is_bank(lines: dict) -> bool:
    return lines.get(B["int_earned"]) is not None and lines.get(B["int_expended"]) is not None


def bank_metrics(lines: dict) -> dict:
    g = lambda k: lines.get(B[k])  # noqa: E731
    pos = lambda k: abs(g(k)) if g(k) is not None else None  # noqa: E731  (BSE files these ratios with a minus sign)
    ie, iex, oi = g("int_earned"), g("int_expended"), g("other_income")
    nii = ie + iex if ie is not None and iex is not None else None  # interest expended is negative
    opex = -(g("emp") + g("oth")) if g("emp") is not None and g("oth") is not None else None
    income = nii + oi if nii is not None and oi is not None else None
    ppop, prov, pbt, tax, pat = g("ppop"), pos("prov"), g("pbt"), g("tax"), g("pat")
    gnpa, nnpa = pos("gnpa"), pos("nnpa")
    return {
        "revenue": ie, "nii": _r(nii, 2), "other_income": oi, "operating_expenses": _r(opex, 2), "ppop": ppop, "provisions": prov,
        "pbt": pbt, "pat": pat, "net_profit": g("net"), "eps": g("eps"),
        "cost_to_income": _r(_ratio(opex, income)), "credit_cost_share_of_ppop": _r(_ratio(prov, ppop)),
        "non_interest_income_share": _r(_ratio(oi, income)), "pat_margin": _r(_ratio(pat, ie)),
        "tax_rate": _r(_ratio(-tax if tax is not None else None, pbt)),
        "gross_npa_pct": pos("gnpa_pct"), "net_npa_pct": pos("nnpa_pct"),
        "npa_coverage": _r(1 - nnpa / gnpa) if gnpa and nnpa is not None else None,
        "roa_pct": g("roa"), "cet1_pct": pos("cet1"),
    }


def _month_index(period_end: str) -> int | None:
    m = re.fullmatch(r"\d+-(\w{3})-(\d{2})", period_end or "")
    return (2000 + int(m.group(2))) * 12 + MONTHS.index(m.group(1)) if m and m.group(1) in MONTHS else None


GROWTH_KEYS = ("revenue", "ebitda", "pbt", "pat", "eps")
# kind -> (growth keys, TTM sums, TTM ratios as (name, numerator, denominator), margin whose change is reported in points)
KINDS = {
    "company": (GROWTH_KEYS, ("revenue", "ebitda", "pbt", "pat", "net_profit", "eps", "other_income"),
                (("ebitda_margin", "ebitda", "revenue"), ("pat_margin", "pat", "revenue")), "ebitda_margin"),
    "bank": (("revenue", "nii", "ppop", "pat", "eps"), ("revenue", "nii", "other_income", "operating_expenses", "ppop", "provisions", "pbt",
                                                       "pat", "net_profit", "eps"),
             (("pat_margin", "pat", "revenue"), ("credit_cost_share_of_ppop", "provisions", "ppop")), "cost_to_income"),
}


def fundamentals(quarters: list[dict]) -> dict:
    """quarters: get_financials()['quarters'] (newest first). Adds metrics, YoY/QoQ growth and TTM.

    A bank's filings have no sales or EBITDA lines, so banks get bank metrics (NII, PPOP, NPAs, ...) instead."""
    kind = "bank" if quarters and is_bank(quarters[0].get("lines") or {}) else "company"
    growth_keys, _, _, margin = KINDS[kind]
    metrics = bank_metrics if kind == "bank" else quarter_metrics
    rows = []
    for q in quarters:
        mi = _month_index(q.get("period_end"))
        if mi is None:
            continue
        rows.append({"quarter": q.get("quarter"), "period": q.get("period"), "period_end": q["period_end"], "_m": mi,
                     "metrics": metrics(q.get("lines") or {})})
    by_m = {r["_m"]: r for r in rows}
    for r in rows:
        for label, back in (("yoy", 12), ("qoq", 3)):
            prev = by_m.get(r["_m"] - back)
            r[label] = {k: _r(_growth(r["metrics"][k], prev["metrics"][k])) for k in growth_keys} if prev else None
            if prev:
                r[label][f"{margin}_change_pts"] = _r(_pts(r["metrics"][margin], prev["metrics"][margin]), 2)
    out = {"kind": kind, "quarters": [{k: v for k, v in r.items() if k != "_m"} for r in rows]}
    out["ttm"] = _ttm(by_m, rows[0]["_m"], kind) if rows else {"available": False, "reason": "no quarters"}
    if out["ttm"].get("available"):
        prior = _ttm(by_m, rows[0]["_m"] - 12, kind)
        out["ttm"]["growth_vs_prior_ttm"] = ({k: _r(_growth(out["ttm"][k], prior[k])) for k in growth_keys} if prior.get("available")
                                             else None)
    return out


def _pts(a, b):
    return (a - b) * 100 if a is not None and b is not None else None


def _ttm(by_m: dict, latest_m: int, kind: str = "company") -> dict:
    window = [by_m.get(latest_m - 3 * i) for i in range(4)]
    if any(w is None for w in window):
        missing = [MONTHS[(latest_m - 3 * i) % 12] + "-" + str((latest_m - 3 * i) // 12)[-2:] for i, w in enumerate(window) if w is None]
        return {"available": False, "reason": f"needs 4 consecutive quarters; missing quarter(s) ending {', '.join(missing)} (ask for more quarters)"}
    _, sums, ratios, _ = KINDS[kind]
    t = {}
    for k in sums:
        vals = [w["metrics"][k] for w in window]
        t[k] = _r(sum(vals), 2) if all(v is not None for v in vals) else None
    t.update({"available": True, "quarters": [w["period"] or w["quarter"] for w in window]})
    t.update({name: _r(_ratio(t[a], t[b])) for name, a, b in ratios})
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
    "returns": "close-to-close change over the last N bars (daily: 1w=5, 1m=21, 3m=63, 6m=126, 1y=252, 3y=756, 5y=1260; weekly: 1m=4, 3m=13, 6m=26, 1y=52, 3y=156, 5y=260)",
    "cagr": "compound annual growth from the first to the last close (calendar days when dates are given, else bars per year)",
    "volatility_annualised": "sample standard deviation of log returns over the last year of bars (or all, if fewer) x sqrt(bars per year)",
    "max_drawdown": "largest peak-to-trough fall in the closes",
    "sma": "simple moving average of the last N closes",
    "ema": "exponential moving average, weight 2/(N+1), seeded with the SMA of the first N closes",
    "macd": "EMA12 - EMA26; signal = EMA9 of MACD; histogram = MACD - signal",
    "rsi_14": "Wilder's RSI: 100 - 100/(1 + average gain / average loss), Wilder-smoothed over 14 periods",
    "bollinger_20_2": "SMA20 +/- 2 population standard deviations of the last 20 closes; percent_b = (close - lower)/(upper - lower)",
    "range_52w": "high and low of the last year of bars (highs/lows when given, else closes)",
    "trend": "SMA50 against SMA200: 'golden cross' state when above, 'death cross' state when below",
    "atr_14": "Wilder's average true range; true range = max(high - low, |high - previous close|, |low - previous close|)",
    "adx_14": "Wilder's ADX with +DI/-DI from directional movement; under 20 weak trend, 20-25 emerging, over 25 trending",
    "stochastic_14_3": "%K = (close - lowest low of 14) / (highest high of 14 - lowest low of 14) x 100; %D = 3-bar SMA of %K",
    "chandelier_exit_22_3": "long: highest high of 22 bars - 3 x ATR(22); short: lowest low of 22 bars + 3 x ATR(22)",
    "pivots_classic": "from the last bar's high/low/close: P = (H+L+C)/3, R1 = 2P-L, S1 = 2P-H, R2 = P+(H-L), S2 = P-(H-L), R3 = H+2(P-L), S3 = L-2(H-P)",
    "swings": "swing high/low = a bar whose high (low) is above (below) the 2 bars on each side (closes when no highs/lows are given); rsi = RSI(14) at that bar",
    "fibonacci": "from the highest high and lowest low of the lookback window: retracements measured back from the end of the move; extensions = start of the move + move x ratio; pullback.projections = end of the pullback (point C) + move x ratio, the usual swing-target convention",
    "rsi_divergence": "comparing the last two swing lows (highs) with RSI(14) at those bars: regular bullish = lower price low with higher RSI low; hidden bullish = higher price low with lower RSI low; bearish mirror on swing highs",
    "volume": "last bar's volume against the 20-bar average",
    "since_entry": "from the bars on or after entry_date: highest close/high (long) or lowest close/low (short); atr_trail = highest close - ATR(14) x multiple; chandelier_since_entry = highest high - 3 x ATR(14); structure_trail = latest swing low since entry (mirror for shorts)",
    "price_jumps": "one-bar moves of 25% or more in the daily closes given; a split or bonus in a series that isn't adjusted for it looks like this",
    "weekly": "weekly bars built from the daily series by ISO week: last close, highest high, lowest low, summed volume; dated by the week's last trading day",
}
WINDOWS = {"daily": {"1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260},
           "weekly": {"1m": 4, "3m": 13, "6m": 26, "1y": 52, "3y": 156, "5y": 260}}
BARS_PER_YEAR = {"daily": 252, "weekly": 52}


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


def rsi_series(xs: list[float], n: int = 14) -> list[float | None]:
    """Wilder RSI aligned with xs (None for the first n bars)."""
    out: list[float | None] = [None] * len(xs)
    if len(xs) < n + 1:
        return out
    ch = [b - a for a, b in zip(xs, xs[1:])]
    gain = sum(max(c, 0) for c in ch[:n]) / n
    loss = sum(max(-c, 0) for c in ch[:n]) / n

    def val(g, l):
        return (100.0 if g > 0 else 50.0) if l == 0 else 100 - 100 / (1 + g / l)

    out[n] = val(gain, loss)
    for i, c in enumerate(ch[n:], start=n + 1):
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
        out[i] = val(gain, loss)
    return out


def rsi(xs: list[float], n: int = 14) -> float | None:
    return rsi_series(xs, n)[-1] if len(xs) >= n + 1 else None


def true_ranges(h: list[float], l: list[float], c: list[float]) -> list[float]:
    return [h[0] - l[0]] + [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]


def atr(h, l, c, n: int = 14) -> float | None:
    tr = true_ranges(h, l, c)
    if len(tr) < n:
        return None
    a = sum(tr[:n]) / n
    for x in tr[n:]:
        a = (a * (n - 1) + x) / n
    return a


def adx(h, l, c, n: int = 14) -> dict | None:
    if len(c) < 2 * n:
        return None
    pdm, mdm, tr = [], [], []
    for i in range(1, len(c)):
        up, down = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if up > down and up > 0 else 0.0)
        mdm.append(down if down > up and down > 0 else 0.0)
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    sp, sm, st = sum(pdm[:n]), sum(mdm[:n]), sum(tr[:n])
    dxs, pdi, mdi = [], 0.0, 0.0
    for i in range(n - 1, len(tr)):
        if i >= n:
            sp, sm, st = sp - sp / n + pdm[i], sm - sm / n + mdm[i], st - st / n + tr[i]
        pdi, mdi = (100 * sp / st, 100 * sm / st) if st else (0.0, 0.0)
        dxs.append(100 * abs(pdi - mdi) / (pdi + mdi) if pdi + mdi else 0.0)
    if len(dxs) < n:
        return None
    a = sum(dxs[:n]) / n
    for x in dxs[n:]:
        a = (a * (n - 1) + x) / n
    strength = "weak or no trend" if a < 20 else "emerging trend" if a < 25 else "trending"
    return {"adx": _r(a, 2), "plus_di": _r(pdi, 2), "minus_di": _r(mdi, 2), "strength": strength,
            "direction": "up (+DI above -DI)" if pdi > mdi else "down (-DI above +DI)" if mdi > pdi else "flat"}


def stochastic(h, l, c, n: int = 14, d: int = 3) -> dict | None:
    if len(c) < n + d - 1:
        return None
    ks = []
    for i in range(len(c) - d, len(c)):
        hh, ll = max(h[i - n + 1:i + 1]), min(l[i - n + 1:i + 1])
        ks.append(100 * (c[i] - ll) / (hh - ll) if hh > ll else 50.0)
    return {"k": _r(ks[-1], 2), "d": _r(sum(ks) / d, 2)}


def swings(h: list[float], l: list[float], dates=None, k: int = 2) -> dict:
    d = (lambda i: dates[i] if dates else i)  # noqa: E731
    highs = [{"at": d(i), "price": h[i], "_i": i} for i in range(k, len(h) - k)
             if all(h[i] > h[j] for j in range(i - k, i)) and all(h[i] > h[j] for j in range(i + 1, i + k + 1))]
    lows = [{"at": d(i), "price": l[i], "_i": i} for i in range(k, len(l) - k)
            if all(l[i] < l[j] for j in range(i - k, i)) and all(l[i] < l[j] for j in range(i + 1, i + k + 1))]
    return {"highs": highs, "lows": lows}


def fibonacci(h: list[float], l: list[float], last: float, dates=None, lookback: int = 126) -> dict | None:
    hw, lw = h[-lookback:], l[-lookback:]
    if len(hw) < 3:
        return None
    off = len(h) - len(hw)
    hi_i, lo_i = off + hw.index(max(hw)), off + lw.index(min(lw))
    hi, lo = h[hi_i], l[lo_i]
    rng = hi - lo
    if rng <= 0:
        return None
    up = lo_i < hi_i  # the move ran from the low up to the high
    ret = {f"{r * 100:g}%": _r(hi - rng * r if up else lo + rng * r, 2) for r in (0.236, 0.382, 0.5, 0.618, 0.786)}
    ext = {f"{r * 100:g}%": _r(lo + rng * r if up else hi - rng * r, 2) for r in (1.272, 1.618, 2.0, 2.618)}
    d = (lambda i: dates[i] if dates else i)  # noqa: E731
    out = {"move": "up" if up else "down", "swing_low": {"at": d(lo_i), "price": lo}, "swing_high": {"at": d(hi_i), "price": hi},
           "retracements": ret, "extensions": ext, "retraced_so_far": _r((hi - last) / rng if up else (last - lo) / rng),
           "lookback_bars": len(hw), "pullback": None}
    # Projections from the end of the pullback (point C), the convention most swing-trading texts use:
    # C + move x ratio in an up move (C - move x ratio in a down move). Only once a pullback has begun.
    end_i = hi_i if up else lo_i
    after = (l if up else h)[end_i + 1:]
    if after:
        c_i = end_i + 1 + (after.index(min(after)) if up else after.index(max(after)))
        c = (l if up else h)[c_i]
        if (up and c < hi) or (not up and c > lo):
            out["pullback"] = {"at": d(c_i), "price": c,
                               "projections": {f"{r * 100:g}%": _r(c + rng * r if up else c - rng * r, 2) for r in (1.0, 1.272, 1.618, 2.0)}}
    return out


def rsi_divergence(closes, h, l, dates=None, lookback: int = 90) -> list[dict]:
    rs = rsi_series(closes)
    sw = swings(h, l, dates)
    start = len(closes) - lookback
    found = []
    for kind, pts, cmp_price in (("bullish", sw["lows"], "low"), ("bearish", sw["highs"], "high")):
        pts = [p for p in pts if p["_i"] >= start and rs[p["_i"]] is not None]
        if len(pts) < 2:
            continue
        a, b = pts[-2], pts[-1]
        ra, rb = rs[a["_i"]], rs[b["_i"]]
        if kind == "bullish":
            typ = "regular" if b["price"] < a["price"] and rb > ra else "hidden" if b["price"] > a["price"] and rb < ra else None
        else:
            typ = "regular" if b["price"] > a["price"] and rb < ra else "hidden" if b["price"] < a["price"] and rb > ra else None
        if typ:
            found.append({"type": f"{typ} {kind}", "points": [{"at": p["at"], "price": p["price"], "rsi": _r(rs[p["_i"]], 2)} for p in (a, b)]})
    return found


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


def to_weekly(dates, closes, highs, lows, volumes):
    """Daily bars -> weekly bars by ISO week."""
    out = {"dates": [], "closes": [], "highs": [], "lows": [], "volumes": [] if volumes is not None else None}
    key_prev = None
    for i, ds in enumerate(dates):
        key = _parse_date(str(ds)).isocalendar()[:2]
        if key != key_prev:
            out["dates"].append(ds), out["closes"].append(closes[i]), out["highs"].append(highs[i]), out["lows"].append(lows[i])
            if volumes is not None:
                out["volumes"].append(volumes[i])
            key_prev = key
        else:
            out["dates"][-1], out["closes"][-1] = ds, closes[i]
            out["highs"][-1], out["lows"][-1] = max(out["highs"][-1], highs[i]), min(out["lows"][-1], lows[i])
            if volumes is not None:
                out["volumes"][-1] += volumes[i]
    return out


def _series(name, vals, n):
    if vals is None:
        return None
    xs = [float(v) for v in vals]
    if len(xs) != n:
        raise ValueError(f"{name} ({len(xs)}) and closes ({n}) differ in length")
    if any(not math.isfinite(x) or x < 0 for x in xs):
        raise ValueError(f"{name} must be non-negative numbers")
    return xs


def since_entry(closes, H, Lo, dates, entry_date: str, side: str = "long", atr14: float | None = None) -> dict:
    """Trailing-stop reference levels from the bars on or after entry_date."""
    start = _parse_date(entry_date)
    idx = [i for i, ds in enumerate(dates) if _parse_date(str(ds)) >= start]
    if not idx:
        raise ValueError(f"entry_date {entry_date} is after the last bar")
    i0 = idx[0]
    c, h, lo = closes[i0:], H[i0:], Lo[i0:]
    out = {"entry_date": entry_date, "first_bar": dates[i0], "bars": len(c)}
    sw = swings(H, Lo, dates)
    if side == "long":
        out.update({"highest_close": max(c), "highest_high": max(h)})
        lows_since = [p for p in sw["lows"] if p["_i"] >= i0]
        out["structure_trail"] = {"at": lows_since[-1]["at"], "price": lows_since[-1]["price"]} if lows_since else None
        if atr14 is not None:
            out["atr_trail"] = {f"{m:g}x": _r(max(c) - m * atr14, 2) for m in (1.5, 2.0, 3.0)}
            out["chandelier_since_entry"] = _r(max(h) - 3 * atr14, 2)
    else:
        out.update({"lowest_close": min(c), "lowest_low": min(lo)})
        highs_since = [p for p in sw["highs"] if p["_i"] >= i0]
        out["structure_trail"] = {"at": highs_since[-1]["at"], "price": highs_since[-1]["price"]} if highs_since else None
        if atr14 is not None:
            out["atr_trail"] = {f"{m:g}x": _r(min(c) + m * atr14, 2) for m in (1.5, 2.0, 3.0)}
            out["chandelier_since_entry"] = _r(min(lo) + 3 * atr14, 2)
    if atr14 is None:
        out["atr_levels"] = "pass highs and lows for the ATR trail and chandelier levels"
    return out


def technicals(closes: list[float], dates: list[str] | None = None, highs=None, lows=None, volumes=None,
               timeframe: str = "daily", entry_date: str | None = None, side: str = "long") -> dict:
    """Indicators on a price series, oldest first. Raises ValueError on input that can't be right."""
    xs = [float(c) for c in closes]
    if len(xs) < 2:
        raise ValueError("need at least 2 closes")
    if any(not math.isfinite(x) or x <= 0 for x in xs):
        raise ValueError("closes must be positive numbers")
    if timeframe not in ("daily", "weekly"):
        raise ValueError("timeframe must be 'daily' or 'weekly'")
    if dates is not None:
        if len(dates) != len(xs):
            raise ValueError(f"dates ({len(dates)}) and closes ({len(xs)}) differ in length")
        parsed = [_parse_date(str(d)) for d in dates]
        if any(b <= a for a, b in zip(parsed, parsed[1:])):
            raise ValueError("dates must be strictly increasing: pass the series oldest first")
    hs, ls, vs = _series("highs", highs, len(xs)), _series("lows", lows, len(xs)), _series("volumes", volumes, len(xs))
    if (hs is None) != (ls is None):
        raise ValueError("pass highs and lows together")
    if hs is not None and any(h < l or not (l <= c <= h) for h, l, c in zip(hs, ls, xs)):
        raise ValueError("each bar needs low <= close <= high")
    # Checked on the daily input, before any weekly grouping: that is where an unadjusted split shows as one bar.
    jumps = [{"at": dates[i] if dates is not None else i, "change": _r(xs[i] / xs[i - 1] - 1)}
             for i in range(1, len(xs)) if abs(xs[i] / xs[i - 1] - 1) >= 0.25]
    if timeframe == "weekly":
        if dates is None:
            raise ValueError("timeframe='weekly' needs the daily dates to group bars into weeks")
        w = to_weekly(list(dates), xs, hs or xs, ls or xs, vs)
        dates, xs, vs = w["dates"], w["closes"], w["volumes"]
        hs, ls = (w["highs"], w["lows"]) if hs is not None else (None, None)
        parsed = [_parse_date(str(d)) for d in dates]
    have_hl = hs is not None
    H, Lo = (hs, ls) if have_hl else (xs, xs)
    bpy = BARS_PER_YEAR[timeframe]
    last = xs[-1]
    rets = {k: _r(last / xs[-1 - n] - 1) for k, n in WINDOWS[timeframe].items() if len(xs) > n}
    years = (parsed[-1] - parsed[0]).days / 365.25 if dates is not None else (len(xs) - 1) / bpy
    cagr = _r((last / xs[0]) ** (1 / years) - 1) if years >= 1 else None
    logr = [math.log(b / a) for a, b in zip(xs, xs[1:])][-bpy:]
    vol = _r(statistics.stdev(logr) * math.sqrt(bpy)) if len(logr) >= 2 else None
    e12, e26, e50 = ema_series(xs, 12), ema_series(xs, 26), ema_series(xs, 50)
    macd = None
    if e26:
        line = [a - b for a, b in zip(e12[len(e12) - len(e26):], e26)]
        sig = ema_series(line, 9)
        if sig:
            macd = {"macd": _r(line[-1], 4), "signal": _r(sig[-1], 4), "histogram": _r(line[-1] - sig[-1], 4)}
    boll = None
    if len(xs) >= 20:
        win = xs[-20:]
        mid, sd = sum(win) / 20, statistics.pstdev(win)
        up, lo = mid + 2 * sd, mid - 2 * sd
        boll = {"middle": _r(mid, 2), "upper": _r(up, 2), "lower": _r(lo, 2),
                "percent_b": _r((last - lo) / (up - lo)) if up > lo else None, "bandwidth": _r((up - lo) / mid)}
    hi, lo52 = max(H[-bpy:]), min(Lo[-bpy:])
    s50, s200 = sma(xs, 50), sma(xs, 200)
    out = {
        "timeframe": timeframe, "count": len(xs), "from": dates[0] if dates else None, "to": dates[-1] if dates else None, "last_close": last,
        "returns": rets, "cagr": cagr, "volatility_annualised": vol, "max_drawdown": max_drawdown(xs, dates),
        "max_drawdown_1y": max_drawdown(xs[-bpy:], dates[-bpy:] if dates else None),
        "sma": {f"sma_{n}": _r(sma(xs, n), 2) for n in (20, 50, 200)},
        "price_vs_sma": {f"vs_sma_{n}": _r(_ratio(last, sma(xs, n)) - 1) if sma(xs, n) else None for n in (20, 50, 200)},
        "ema": {"ema_12": _r(e12[-1], 2) if e12 else None, "ema_26": _r(e26[-1], 2) if e26 else None,
                "ema_50": _r(e50[-1], 2) if e50 else None},
        "macd": macd, "rsi_14": _r(rsi(xs), 2), "bollinger_20_2": boll,
        "range_52w": {"high": hi, "low": lo52, "position": _r((last - lo52) / (hi - lo52)) if hi > lo52 else None,
                      "below_high": _r(last / hi - 1), "window_bars": len(xs[-bpy:])},
        "trend": ({"sma50_vs_sma200": _r(s50 / s200 - 1), "state": "golden cross (SMA50 above SMA200)" if s50 > s200 else "death cross (SMA50 below SMA200)"}
                  if s50 and s200 else None),
    }
    if jumps:
        out["price_jumps"] = {"bars": jumps[-5:], "note": "If any of these is a split or bonus, the earlier prices aren't adjusted for it and "
                              "every indicator spanning it is wrong: divide the earlier prices by the ratio (multiply the volumes), "
                              "or start the series after it."}
    sw, rs = swings(H, Lo, dates), rsi_series(xs)
    out["swings"] = {side: [{"at": p["at"], "price": p["price"], "rsi": _r(rs[p["_i"]], 2)} for p in sw[side][-5:]] for side in ("highs", "lows")}
    out["fibonacci"] = fibonacci(H, Lo, last, dates, lookback=126 if timeframe == "daily" else 52)
    out["rsi_divergence"] = rsi_divergence(xs, H, Lo, dates, lookback=90 if timeframe == "daily" else 52)
    if have_hl:
        a14, a22 = atr(H, Lo, xs, 14), atr(H, Lo, xs, 22)
        out["atr_14"] = _r(a14, 2)
        out["atr_14_pct"] = _r(_ratio(a14, last))
        out["adx_14"] = adx(H, Lo, xs, 14)
        out["stochastic_14_3"] = stochastic(H, Lo, xs)
        out["chandelier_exit_22_3"] = ({"long": _r(max(H[-22:]) - 3 * a22, 2), "short": _r(min(Lo[-22:]) + 3 * a22, 2)} if a22 is not None else None)
        P = (H[-1] + Lo[-1] + last) / 3
        out["pivots_classic"] = {k: _r(v, 2) for k, v in {"P": P, "R1": 2 * P - Lo[-1], "S1": 2 * P - H[-1], "R2": P + (H[-1] - Lo[-1]),
                                                           "S2": P - (H[-1] - Lo[-1]), "R3": H[-1] + 2 * (P - Lo[-1]), "S3": Lo[-1] - 2 * (H[-1] - P)}.items()}
    else:
        out["ohlc_indicators"] = "pass highs and lows for ATR, ADX, stochastic, chandelier exit and pivots"
    if entry_date:
        if dates is None:
            raise ValueError("entry_date needs dates")
        if side not in ("long", "short"):
            raise ValueError("side must be 'long' or 'short'")
        out["since_entry"] = since_entry(xs, H, Lo, dates, entry_date, side, atr(H, Lo, xs, 14) if have_hl else None)
    if vs is not None and len(vs) >= 20:
        avg20 = sum(vs[-20:]) / 20
        out["volume"] = {"last": vs[-1], "avg_20": _r(avg20, 2), "last_vs_avg_20": _r(_ratio(vs[-1], avg20))}
    need = [("sma_200 / trend", 200), ("1y range and volatility", bpy), ("adx", 28), ("macd", 34), ("rsi_14", 15), ("bollinger", 20)]
    missing = [name for name, n in need if len(xs) < n]
    if missing:
        out["needs_more_data"] = (f"{len(xs)} {timeframe} bars; for {', '.join(missing)} pass more history "
                                  f"(about {bpy + 10} {timeframe} bars covers everything except 3y/5y returns)")
    return out
