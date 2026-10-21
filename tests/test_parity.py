"""The Worker (worker/worker.js) re-implements the analysis in JavaScript; the same inputs must give the same outputs."""
import json
import math
import shutil
import subprocess
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from bse_mcp import analysis, tools

from . import fixtures as F
from .test_analysis import SBI_Q1FY27

NODE = shutil.which("node")
WORKER = Path(__file__).resolve().parent.parent / "worker" / "worker.js"
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not installed")

RUNNER = """
import { sessionStatus, fundamentals, technicals, positionSize } from %s;
const cases = JSON.parse(await new Promise((ok) => { let s = ""; process.stdin.on("data", (d) => (s += d)); process.stdin.on("end", () => ok(s)); }));
const run = {
  session: ([stamp, refs, now]) => sessionStatus(stamp, refs, new Date(now)),
  fundamentals: ([qs]) => fundamentals(qs),
  technicals: ([c, d, h, l, v, tf, e, side]) => technicals(c, d, h, l, v, tf, e, side),
  position_size: ([kw]) => positionSize(kw),
};
process.stdout.write(JSON.stringify(cases.map(([kind, args]) => run[kind](args))));
"""


def js(cases):
    out = subprocess.run([NODE, "--input-type=module", "-e", RUNNER % json.dumps(WORKER.as_uri())], input=json.dumps(cases),
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def last_digit(x: float) -> float:
    """The unit of x's last decimal digit as printed: 0.01 for 249780.57."""
    text = repr(float(x))
    return 10.0 ** -len(text.split(".")[1]) if "." in text and "e" not in text else 0.0


def same(a, b, path="$"):
    """Equal as JSON. Numbers may differ in their last bits, or by one in the last digit where a value rounded to N places
    sat on a half: Python's round() and JavaScript's Math.round() break those ties differently."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        tie = abs(a - b) <= max(last_digit(a), last_digit(b)) * (1 + 1e-9)
        assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9) or tie, f"{path}: python {a} != js {b}"
    elif isinstance(a, dict) and isinstance(b, dict):
        assert set(a) == set(b), f"{path}: keys only in python {sorted(set(a) - set(b))}, only in js {sorted(set(b) - set(a))}"
        for k in a:
            same(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list) and isinstance(b, list):
        assert len(a) == len(b), f"{path}: lengths {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            same(x, y, f"{path}[{i}]")
    else:
        assert a == b, f"{path}: python {a!r} != js {b!r}"


def norm(x):
    return json.loads(json.dumps(x))


def compare(cases, python_results):
    for case, py, got in zip(cases, python_results, js(cases)):
        same(norm(py), got, f"{case[0]}")


def test_session_status_matches():
    stamps = [("19 Oct 26 | 09:07", [], "2026-10-19T09:05:00+05:30"), ("19 Oct 26 | 09:07", [], "2026-10-19T12:00:00+05:30"),
              ("19 Oct 26 | 15:31", [], "2026-10-19T18:00:00+05:30"), ("22 Jun 23 | 16:00", ["19 Oct 26 | 11:59"], "2026-10-19T12:00:00+05:30"),
              ("16 Oct 26 | 16:00", ["16 Oct 26 | 16:00", "16 Oct 26 | 16:00"], "2026-10-19T12:00:00+05:30"),
              ("16 Oct 26 | 16:00", ["16 Oct 26 | 16:00"], "2026-10-17T08:00:00+05:30"), ("16 Oct 26 | 16:00", ["16 Oct 26 | 16:00"], "2026-10-19T08:00:00+05:30"),
              ("16 Oct 26 | 16:00", [None, None], "2026-10-19T12:00:00+05:30"), ("yesterday", [], "2026-10-19T12:00:00+05:30"),
              (None, [], "2026-10-19T12:00:00+05:30"), ("19 Oct 26 | 11:00", [], "2026-10-19T00:30:00+00:00")]  # 06:00 IST, given in UTC
    cases = [["session", list(c)] for c in stamps]
    compare(cases, [tools.session_status(s, r, datetime.fromisoformat(n)) for s, r, n in stamps])


def quarters_from_fixtures():
    out = []
    for qid in ("130.00", "129.00", "128.00", "127.00", "126.00"):
        typ, begin, end, vals = F.Q[qid]
        out.append({"quarter": tools.label_from_end(end), "period": tools.period_label(begin, end), "period_end": end, "type": typ,
                    "lines": dict(zip(F.LINES, vals))})
    return out


def bank_quarters():
    ends = ["30-Jun-26", "31-Mar-26", "31-Dec-25", "30-Sep-25", "30-Jun-25", "31-Mar-25", "31-Dec-24", "30-Sep-24"]
    return [{"quarter": f"q{i}", "period": f"p{i}", "period_end": e,
             "lines": {k: v * (1 - 0.03 * i) for k, v in SBI_Q1FY27.items()}} for i, e in enumerate(ends)]


def test_fundamentals_match_for_companies_and_banks():
    sets = [quarters_from_fixtures(), bank_quarters(), quarters_from_fixtures()[:1], []]
    compare([["fundamentals", [qs]] for qs in sets], [analysis.fundamentals(qs) for qs in sets])


def series(n, seed=7):
    day, dates, closes, highs, lows, vols = date(2025, 1, 1), [], [], [], [], []
    x = 1000.0
    while len(dates) < n:
        if day.weekday() < 5:
            seed = (seed * 1103515245 + 12345) % 2 ** 31
            x *= 1 + ((seed % 2001) - 1000) / 40000
            dates.append(day.isoformat()), closes.append(round(x, 2)), highs.append(round(x * 1.012, 2)), lows.append(round(x * 0.988, 2))
            vols.append(float(10000 + seed % 5000))
        day += timedelta(days=1)
    return dates, closes, highs, lows, vols


def test_technicals_match():
    d, c, h, l, v = series(300)
    args = [[c, d, h, l, v, "daily", None, "long"], [c, d, h, l, v, "weekly", None, "long"], [c, d, None, None, v, "daily", None, "long"],
            [c, d, h, l, v, "daily", d[250], "short"], [c[:40], None, None, None, None, "daily", None, "long"]]
    compare([["technicals", a] for a in args], [analysis.technicals(*a) for a in args])


def test_position_size_matches():
    kws = [dict(capital=1_000_000, entry=1800, stop=1700, risk_pct=2), dict(capital=500_000, entry=1000, side="short", atr=20, atr_multiplier=1.5, target=900, max_position_pct=100),
           dict(capital=1_000_000, entry=1800, stop=1700, risk_pct=2, max_position_pct=100, target=2000, win_rate=0.45, brokerage_per_order=20, brokerage_pct=0.0003),
           dict(capital=200_000, entry=250, stop=240, segment="intraday", exchange="BSE", leverage=5, dp_charge=15)]
    compare([["position_size", [kw]] for kw in kws], [tools.position_size(**kw) for kw in kws])  # the tool adds the note in Python
