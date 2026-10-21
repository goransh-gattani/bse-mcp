"""The analysis journal: recording verdicts, snapshots, and scoring them only on prices after the call."""
import json
from datetime import datetime

import pytest

from bse_mcp import journal as J, nse, server, tools
from bse_mcp.tools import IST, ArgError

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=IST)


def bars(start_day, closes, spread=5.0):
    """Daily candles on consecutive October days from start_day, high/low `spread` around each close."""
    return [{"date": f"2026-10-{start_day + i:02d}", "open": c, "high": c + spread, "low": c - spread, "close": c, "volume": 1000}
            for i, c in enumerate(closes)]


def verdict(**kw):
    return {"horizon_days": 3, "entry": 100.0, "action": "buy", "stop": None, "target": None, **kw}


def test_evaluate_waits_for_the_horizon_then_measures_from_the_entry():
    assert J.evaluate(verdict(), bars(20, [101, 102])) is None
    out = J.evaluate(verdict(), bars(20, [101, 102, 110, 90]))  # the 4th bar is past the horizon and must not count
    assert out["exit_date"] == "2026-10-22" and out["fwd_return"] == pytest.approx(0.10) and out["directional_return"] == pytest.approx(0.10)
    assert out["max_adverse"] == pytest.approx(-0.04) and out["first_hit"] is None


def test_evaluate_short_and_neutral_calls():
    assert J.evaluate(verdict(action="sell"), bars(20, [99, 98, 95]))["directional_return"] == pytest.approx(0.05)
    out = J.evaluate(verdict(action="hold"), bars(20, [99, 98, 95]))
    assert out["directional_return"] is None and out["fwd_return"] == pytest.approx(-0.05)


@pytest.mark.parametrize("closes, stop, target, first", [
    ([101, 112, 120], 90, 115, "target"),    # day 3's high 125 reaches the target
    ([101, 88, 120], 90, 115, "stop"),       # day 2's low 83 takes the stop before the target
    ([101, 102, 103], 90, 115, "neither"),
    ([101, 102, 103], 98, 106, "ambiguous"),  # day 1 spans 96-106: both levels inside one daily bar
])
def test_evaluate_which_level_was_hit_first(closes, stop, target, first):
    assert J.evaluate(verdict(stop=stop, target=target), bars(20, closes))["first_hit"] == first


def test_record_analysis_saves_the_verdict_with_live_context(fake):
    r = tools.record_analysis("500002", "bse-mcp-trading-toolkit", "BUY", stop=6500, target=7600, rationale="breakout", model="test-model")
    assert r["entry"] == 6963.0 and r["action"] == "buy" and r["session"]["status"] == "market_closed"
    with J.connect() as conn:
        row = conn.execute("SELECT * FROM verdicts").fetchone()
    assert row["skill"] == "bse-mcp-trading-toolkit" and row["nse_symbol"] == "ABB" and row["ltp"] == 6963.0 and row["model"] == "test-model"
    assert row["skill_version"] == J.skill_version("bse-mcp-trading-toolkit") and len(row["skill_version"]) == 12
    assert row["session_status"] == "market_closed" and json.loads(row["quote_json"])["scripcode"] == "500002"


@pytest.mark.parametrize("kw, needle", [
    ({"action": "maybe"}, "action must be"),
    ({"skill": " "}, "skill"),
    ({"horizon_days": 0}, "horizon_days"),
    ({"confidence": 2}, "confidence"),
    ({"stop": 7000}, "stop must be below"),
    ({"action": "sell", "target": 7000}, "target must be below"),
])
def test_record_analysis_rejects_what_cant_be_scored(fake, kw, needle):
    with pytest.raises(ArgError, match=needle):
        tools.record_analysis(**{"scripcode": "500002", "skill": "s", "action": "buy", **kw})


def test_skill_version_changes_with_the_skill(tmp_path):
    (tmp_path / "s").mkdir()
    (tmp_path / "s" / "SKILL.md").write_text("one")
    v1 = J.skill_version("s", tmp_path)
    (tmp_path / "s" / "SKILL.md").write_text("two")
    assert v1 != J.skill_version("s", tmp_path) and J.skill_version("missing", tmp_path) is None


def test_score_uses_only_bars_after_the_verdict_day():
    with J.connect() as conn:
        quote = {"symbol": "ABB", "price": {"ltp": 100.0}, "session": {"status": "live"}}
        J.record(conn, scripcode="500002", skill="s", action="buy", entry=100.0, quote=quote, now=NOW, horizon_days=2, target=104)
        J.save_candles(conn, "ABB", bars(16, [50, 50, 100]), NOW)  # up to and including the verdict day: ignored
        assert "pending (0/2" in J.score(conn, NOW)[0]
        J.save_candles(conn, "ABB", bars(20, [101, 103]), NOW)
        assert "+3.00%" in J.score(conn, NOW)[0]
        o = conn.execute("SELECT * FROM outcomes").fetchone()
        assert o["first_bar"] == "2026-10-20" and o["first_hit"] == "target"
        assert J.score(conn, NOW) == []  # scored once
        rep = J.report(conn)
        assert rep[0]["scored"] == 1 and rep[0]["hit_rate"] == 1.0 and rep[0]["target_first"] == 1
        assert "s " in J.format_report(rep)[1] and J.format_report([]) == ["no verdicts yet"]


def test_score_fetches_candles_once_per_symbol():
    calls = []

    def history(symbol, n):
        calls.append(symbol)
        return bars(20, [101, 102, 103])

    with J.connect() as conn:
        quote = {"symbol": "ABB", "price": {"ltp": 100.0}, "session": {}}
        for _ in range(2):
            J.record(conn, scripcode="500002", skill="s", action="buy", entry=100.0, quote=quote, now=NOW, horizon_days=3)
        lines = J.score(conn, datetime(2026, 10, 23, 18, 0, tzinfo=IST), history)
    assert calls == ["ABB"] and len(lines) == 2


def test_snapshot_records_each_scrip_and_survives_failures():
    def quote(code):
        if code == "999999":
            raise tools.BseError("blocked")
        return {"symbol": "ABB", "price": {"ltp": 100.0}, "session": {"status": "live", "data_as_of": "x"}}

    def history(symbol, n):
        raise nse.NseError("down")

    with J.connect() as conn:
        lines = J.snapshot(conn, [("500002", None), ("999999", "XYZ")], NOW, quote, lambda c: {"rsi_14": 50}, history)
        rows = conn.execute("SELECT * FROM snapshots ORDER BY id").fetchall()
        assert conn.execute("SELECT slot FROM runs").fetchone()[0] == "mid"
    assert rows[0]["session_status"] == "live" and rows[0]["nse_symbol"] == "ABB" and json.loads(rows[0]["prices_json"]) == {"rsi_14": 50}
    assert "blocked" in rows[1]["error"] and "NSE candles failed" in lines[1]


def test_watchlist_file(tmp_path):
    p = tmp_path / "w.txt"
    p.write_text("# mine\n500112 sbin\n500002  # ABB\n\n")
    assert J.read_watchlist(p) == [("500112", "SBIN"), ("500002", None)]


def test_cli_report_and_snapshot_without_watchlist(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "_now", lambda: NOW)
    assert server.main(["report"]) == 0 and "no verdicts yet" in capsys.readouterr().out
    assert server.main(["snapshot", "--watchlist", str(tmp_path / "none.txt")]) == 1
