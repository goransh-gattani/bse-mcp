"""Position sizing, risk/reward and Indian equity trading costs. Pure arithmetic, no BSE access.

Sizing follows the standard fixed-fractional rule: risk a set share of capital between entry and
stop, then cap the position by available capital and a single-stock limit. Cost rates are the
statutory ones for cash equity as published by brokers; they change from time to time, so every
rate can be overridden and the output says which rates were used.
"""

from __future__ import annotations

import math

# Statutory charges for Indian cash equity, as fractions of traded value (rates as listed on
# https://upstox.com/brokerage-charges/ in Oct 2026; NSE's transaction charge was revised to
# 0.00307% from 1 Mar 2026). Brokerage and DP charges depend on the broker: default 0, pass yours.
RATES_AS_OF = "Oct 2026"
RATES_SOURCE = "https://upstox.com/brokerage-charges/"
DEFAULT_RATES = {
    "delivery": {"stt_buy": 0.001, "stt_sell": 0.001, "stamp_buy": 0.00015},
    "intraday": {"stt_buy": 0.0, "stt_sell": 0.00025, "stamp_buy": 0.00003},
    "exchange_txn": {"NSE": 0.0000307, "BSE": None},  # BSE's charge varies by scrip group
    "sebi_fee": 0.000001,  # Rs 10 per crore
    "gst": 0.18,  # on brokerage + exchange transaction charge + SEBI fee
}

DEFINITIONS = {
    "risk_amount": "capital x risk_pct: what you lose if the stop is hit (before costs)",
    "shares": "the smallest of: risk_amount / (entry - stop), capital x leverage / entry, and capital x max_position_pct / entry; rounded down",
    "atr_stop": "when no stop is given: entry - atr x atr_multiplier for a long (plus for a short)",
    "reward_to_risk": "(target - entry) / (entry - stop) per share, before costs; net figures include round-trip costs",
    "expected_value": "win_rate x net gain at target - (1 - win_rate) x net loss at stop, per trade",
    "kelly": "W - (1 - W) / R with W = win rate and R = average win / average loss; half-Kelly is the usual practical cap",
    "costs": "STT, exchange transaction charge, SEBI fee, stamp duty (buy side), brokerage and GST (18% on brokerage + exchange charge + SEBI fee), plus DP charge on delivery sells",
    "breakeven_move": "price move needed to cover the round-trip costs",
}


class SizingError(ValueError):
    pass


def _r(x, nd=2):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else round(x, nd)


def costs(buy_value: float, sell_value: float, segment: str = "delivery", exchange: str = "NSE",
          brokerage_per_order: float = 0.0, brokerage_pct: float = 0.0, dp_charge: float = 0.0,
          exchange_txn_rate: float | None = None) -> dict:
    """Round-trip charges for one buy and one sell, in rupees."""
    if segment not in ("delivery", "intraday"):
        raise SizingError("segment must be 'delivery' or 'intraday'")
    if exchange not in ("NSE", "BSE"):
        raise SizingError("exchange must be 'NSE' or 'BSE'")
    seg = DEFAULT_RATES[segment]
    txn = exchange_txn_rate if exchange_txn_rate is not None else DEFAULT_RATES["exchange_txn"][exchange]
    notes = []
    if txn is None:
        txn = DEFAULT_RATES["exchange_txn"]["NSE"]
        notes.append("BSE's transaction charge varies by scrip group; NSE's rate used as an approximation (pass exchange_txn_rate for the exact one)")
    brokerage = sum(min(brokerage_per_order, v * brokerage_pct) if brokerage_per_order and brokerage_pct else
                    (brokerage_per_order or v * brokerage_pct) for v in (buy_value, sell_value) if v)
    stt = buy_value * seg["stt_buy"] + sell_value * seg["stt_sell"]
    exch = (buy_value + sell_value) * txn
    sebi = (buy_value + sell_value) * DEFAULT_RATES["sebi_fee"]
    stamp = buy_value * seg["stamp_buy"]
    gst = (brokerage + exch + sebi) * DEFAULT_RATES["gst"]
    dp = dp_charge if segment == "delivery" and sell_value else 0.0
    total = brokerage + stt + exch + sebi + stamp + gst + dp
    if not brokerage_per_order and not brokerage_pct:
        notes.append("brokerage assumed 0 (pass brokerage_per_order and/or brokerage_pct for your broker)")
    return {"total": _r(total), "stt": _r(stt), "exchange_txn": _r(exch), "sebi_fee": _r(sebi), "stamp_duty": _r(stamp),
            "brokerage": _r(brokerage), "gst": _r(gst), "dp_charge": _r(dp), "notes": notes}


def position_size(capital: float, entry: float, stop: float | None = None, side: str = "long", risk_pct: float = 1.0,
                  atr: float | None = None, atr_multiplier: float = 2.0, target: float | None = None, leverage: float = 1.0,
                  max_position_pct: float = 20.0, win_rate: float | None = None, avg_win_loss: float | None = None,
                  segment: str = "delivery", exchange: str = "NSE", brokerage_per_order: float = 0.0,
                  brokerage_pct: float = 0.0, dp_charge: float = 0.0, exchange_txn_rate: float | None = None) -> dict:
    if capital <= 0 or entry <= 0:
        raise SizingError("capital and entry must be positive")
    if side not in ("long", "short"):
        raise SizingError("side must be 'long' or 'short'")
    if not 0 < risk_pct <= 10:
        raise SizingError("risk_pct is a percent of capital, between 0 and 10 (1-2 is the usual range)")
    if leverage < 1:
        raise SizingError("leverage must be 1 (none) or more")
    sign = 1 if side == "long" else -1
    stop_basis = "given"
    if stop is None:
        if not atr or atr <= 0:
            raise SizingError("pass a stop price, or atr (and optionally atr_multiplier) to place the stop from volatility")
        stop, stop_basis = entry - sign * atr * atr_multiplier, f"entry {'-' if sign > 0 else '+'} {atr_multiplier} x ATR"
    if sign * (entry - stop) <= 0:
        raise SizingError(f"for a {side} the stop must be {'below' if sign > 0 else 'above'} the entry")
    if target is not None and sign * (target - entry) <= 0:
        raise SizingError(f"for a {side} the target must be {'above' if sign > 0 else 'below'} the entry")
    per_share = abs(entry - stop)
    risk_amount = capital * risk_pct / 100
    by_risk = math.floor(risk_amount / per_share)
    by_capital = math.floor(capital * leverage / entry)
    by_cap = math.floor(capital * max_position_pct / 100 / entry)
    shares = min(by_risk, by_capital, by_cap)
    binding = "risk" if shares == by_risk else "capital (incl. leverage)" if shares == by_capital else f"{max_position_pct:g}% single-stock cap"
    notes = []
    if shares < 1:
        raise SizingError(f"position rounds to 0 shares (binding limit: {binding}); widen risk_pct, tighten the stop, or add capital")
    if leverage > 1:
        notes.append("with leverage a gap through the stop loses more than planned; common practice is to divide risk_pct by the leverage")

    def round_trip(exit_price):
        buy, sell = (entry, exit_price) if sign > 0 else (exit_price, entry)
        return costs(shares * buy, shares * sell, segment, exchange, brokerage_per_order, brokerage_pct, dp_charge, exchange_txn_rate)

    c_stop = round_trip(stop)
    out = {
        "side": side, "entry": entry, "stop": _r(stop), "stop_basis": stop_basis, "risk_per_share": _r(per_share),
        "risk_amount": _r(risk_amount), "shares": shares, "position_value": _r(shares * entry),
        "position_pct_of_capital": _r(shares * entry / capital * 100), "binding_limit": binding,
        "limits": {"by_risk": by_risk, "by_capital": by_capital, "by_single_stock_cap": by_cap},
        "loss_at_stop": {"gross": _r(shares * per_share), "costs": c_stop["total"], "net": _r(shares * per_share + c_stop["total"])},
        "costs_at_stop": c_stop,
        "breakeven_move": _r(round_trip(entry)["total"] / shares, 4),
    }
    if target is not None:
        c_tgt = round_trip(target)
        gain = shares * abs(target - entry)
        out["gain_at_target"] = {"gross": _r(gain), "costs": c_tgt["total"], "net": _r(gain - c_tgt["total"])}
        out["reward_to_risk"] = _r(abs(target - entry) / per_share)
        out["reward_to_risk_net"] = _r((gain - c_tgt["total"]) / out["loss_at_stop"]["net"])
        if win_rate is not None:
            if not 0 < win_rate < 1:
                raise SizingError("win_rate is a fraction between 0 and 1 (e.g. 0.45)")
            ev = win_rate * out["gain_at_target"]["net"] - (1 - win_rate) * out["loss_at_stop"]["net"]
            out["expected_value"] = _r(ev)
            out["breakeven_win_rate"] = _r(out["loss_at_stop"]["net"] / (out["loss_at_stop"]["net"] + out["gain_at_target"]["net"]), 4)
    if win_rate is not None:
        R = avg_win_loss if avg_win_loss else out.get("reward_to_risk")
        if R:
            k = win_rate - (1 - win_rate) / R
            out["kelly"] = {"full": _r(k, 4), "half": _r(k / 2, 4), "R_used": R,
                            "note": "negative means the edge doesn't pay: don't take the trade" if k <= 0 else
                            "fraction of capital to risk per trade; half-Kelly is the usual practical cap"}
    out["rates"] = {"as_of": RATES_AS_OF, "source": RATES_SOURCE, "segment": segment, "exchange": exchange}
    out["notes"] = notes + c_stop["notes"]
    out["definitions"] = DEFINITIONS
    return out
