"""Position sizing and costs, checked against hand calculations."""
import pytest

from bse_mcp import sizing as S, tools
from bse_mcp.tools import ArgError


def test_fixed_fractional_matches_worked_example():
    # Rs 10 lakh, 2% risk, entry 1800, stop 1700 -> 200 shares (36% of capital) when no single-stock cap applies
    r = S.position_size(1_000_000, 1800, 1700, risk_pct=2, max_position_pct=100)
    assert (r["shares"], r["position_value"], r["position_pct_of_capital"], r["binding_limit"]) == (200, 360000, 36.0, "risk")


def test_single_stock_cap_binds_by_default():
    r = S.position_size(1_000_000, 1800, 1700, risk_pct=2)
    assert r["shares"] == 111 and r["binding_limit"] == "20% single-stock cap"
    assert r["limits"] == {"by_risk": 200, "by_capital": 555, "by_single_stock_cap": 111}


def test_delivery_costs_by_hand():
    c = S.costs(360000, 340000)
    exch = 700000 * 0.0000307
    expected = 700 + exch + 0.7 + 54 + (exch + 0.7) * 0.18
    assert c["total"] == round(expected, 2) and c["stt"] == 700 and c["stamp_duty"] == 54


def test_intraday_costs_and_brokerage():
    c = S.costs(100000, 101000, segment="intraday", brokerage_per_order=20, brokerage_pct=0.0003)
    # brokerage = min(20, 0.03% of value) per order = 20 + 20; STT 0.025% on sell only; stamp 0.003% on buy
    exch = 201000 * 0.0000307
    expected = 40 + 101000 * 0.00025 + exch + 0.201 + 100000 * 0.00003 + (40 + exch + 0.201) * 0.18
    assert c["brokerage"] == 40 and c["total"] == round(expected, 2)


def test_atr_stop_short_side_and_target():
    r = S.position_size(500_000, 1000, side="short", atr=20, atr_multiplier=1.5, target=900, max_position_pct=100)
    assert r["stop"] == 1030 and r["stop_basis"] == "entry + 1.5 x ATR" and r["shares"] == 166
    assert r["reward_to_risk"] == round(100 / 30, 2) and r["reward_to_risk_net"] < r["reward_to_risk"]


def test_expected_value_and_kelly():
    r = S.position_size(1_000_000, 1800, 1700, risk_pct=2, max_position_pct=100, target=2000, win_rate=0.45)
    gain, loss = r["gain_at_target"]["net"], r["loss_at_stop"]["net"]
    assert r["expected_value"] == round(0.45 * gain - 0.55 * loss, 2)
    assert r["kelly"]["full"] == round(0.45 - 0.55 / 2.0, 4) and r["kelly"]["half"] == round((0.45 - 0.55 / 2.0) / 2, 4)
    bad = S.position_size(1_000_000, 1800, 1700, win_rate=0.3, avg_win_loss=1.5)
    assert bad["kelly"]["full"] < 0 and "don't take" in bad["kelly"]["note"]


@pytest.mark.parametrize("kwargs, msg", [
    ({"capital": 1e6, "entry": 100, "stop": 110}, "below the entry"),
    ({"capital": 1e6, "entry": 100, "stop": 90, "side": "short"}, "above the entry"),
    ({"capital": 1e6, "entry": 100}, "pass a stop price, or atr"),
    ({"capital": 1e6, "entry": 100, "stop": 90, "target": 95}, "target must be above"),
    ({"capital": 1e6, "entry": 100, "stop": 90, "risk_pct": 25}, "between 0 and 10"),
    ({"capital": 1000, "entry": 5000, "stop": 4000}, "rounds to 0 shares"),
])
def test_rejects_inputs_that_cant_be_right(kwargs, msg):
    with pytest.raises(ArgError, match=msg):
        tools.position_size(**kwargs)
