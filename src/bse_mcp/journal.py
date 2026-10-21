"""The analysis journal: a local SQLite file for judging the trading skills against what prices did next.

    verdicts   what a skill concluded (record_analysis): action, entry, stop, target, horizon, with the live
               price and session status at that moment, the skill's version and the model
    snapshots  get_quote and analyze_prices outputs per scrip, a few times a day (bse-mcp snapshot)
    candles    NSE daily OHLCV kept locally, because the sources only serve recent history
    outcomes   per verdict, once `horizon_days` trading days have closed after it (bse-mcp score)

Raw tool outputs are stored as JSON, so verdicts can be re-scored when the scoring rules change. Scoring
starts from the first trading day after the verdict and never looks at prices from before it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import date, datetime
from pathlib import Path

ACTIONS = {"buy": 1, "sell": -1, "hold": 0, "avoid": 0}  # sell = bearish: short, or exit a long
SKILLS = Path(__file__).parent / "skills"

SCHEMA = """
CREATE TABLE IF NOT EXISTS verdicts (
    id INTEGER PRIMARY KEY, ts TEXT NOT NULL, scripcode TEXT NOT NULL, nse_symbol TEXT, skill TEXT NOT NULL,
    skill_version TEXT, model TEXT, action TEXT NOT NULL, entry REAL NOT NULL, stop REAL, target REAL,
    horizon_days INTEGER NOT NULL, confidence REAL, rationale TEXT, ltp REAL, session_status TEXT, data_as_of TEXT, quote_json TEXT);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, ts TEXT NOT NULL, slot TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id), scripcode TEXT NOT NULL, nse_symbol TEXT,
    session_status TEXT, data_as_of TEXT, ltp REAL, quote_json TEXT, prices_json TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL, close REAL, volume REAL,
    source TEXT NOT NULL DEFAULT 'nse', fetched_at TEXT NOT NULL, PRIMARY KEY (symbol, date, source));
CREATE TABLE IF NOT EXISTS outcomes (
    verdict_id INTEGER PRIMARY KEY REFERENCES verdicts(id), scored_at TEXT NOT NULL, horizon_days INTEGER NOT NULL,
    first_bar TEXT, exit_date TEXT, exit_close REAL, fwd_return REAL, directional_return REAL,
    max_favourable REAL, max_adverse REAL, first_hit TEXT);
"""


def db_path() -> Path:
    return Path(os.environ.get("BSE_MCP_JOURNAL") or Path.home() / ".bse-mcp" / "journal.db").expanduser()


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def skill_version(skill: str, root: Path = SKILLS) -> str | None:
    """A short hash of a packaged skill's files, so results can be told apart when a skill changes."""
    folder = root / skill
    if not (folder / "SKILL.md").is_file():
        return None
    h = hashlib.sha1()
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(folder).as_posix().encode() + b"\0" + p.read_bytes())
    return h.hexdigest()[:12]


def record(conn, *, scripcode: str, skill: str, action: str, entry: float, quote: dict, now: datetime, stop=None, target=None,
           horizon_days: int = 20, confidence=None, rationale: str = "", model=None, nse_symbol=None) -> int:
    session = quote.get("session") or {}
    cur = conn.execute(
        "INSERT INTO verdicts (ts, scripcode, nse_symbol, skill, skill_version, model, action, entry, stop, target, horizon_days, "
        "confidence, rationale, ltp, session_status, data_as_of, quote_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (now.isoformat(timespec="seconds"), scripcode, nse_symbol or quote.get("symbol"), skill, skill_version(skill), model, action,
         entry, stop, target, horizon_days, confidence, rationale, (quote.get("price") or {}).get("ltp"), session.get("status"),
         session.get("data_as_of"), json.dumps(quote, default=str)))
    conn.commit()
    return cur.lastrowid


def slot_for(now: datetime) -> str:
    """Which of the day's runs this is, by the IST clock: open (before 11:00), mid (before 14:00), close."""
    return "open" if now.hour < 11 else "mid" if now.hour < 14 else "close"


def save_candles(conn, symbol: str, rows: list[dict], now: datetime, source: str = "nse") -> int:
    conn.executemany("INSERT OR REPLACE INTO candles (symbol, date, open, high, low, close, volume, source, fetched_at) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     [(symbol, r["date"], r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"), source,
                       now.isoformat(timespec="seconds")) for r in rows])
    conn.commit()
    return len(rows)


def candles(conn, symbol: str, after: str | None = None, source: str = "nse") -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM candles WHERE symbol = ? AND source = ? AND date > ? ORDER BY date",
                        (symbol, source, after or "")).fetchall()


def snapshot(conn, watchlist: list[tuple[str, str | None]], now: datetime, quote_fn, prices_fn, history_fn=None) -> list[str]:
    """One run over the watchlist: quote and price analysis from BSE, and NSE candles when history_fn is given."""
    run = conn.execute("INSERT INTO runs (ts, slot) VALUES (?, ?)", (now.isoformat(timespec="seconds"), slot_for(now))).lastrowid
    lines = [f"run {run} ({slot_for(now)}) at {now.isoformat(timespec='minutes')}"]
    for code, symbol in watchlist:
        quote = prices = error = None
        try:
            quote = quote_fn(code)
            prices = prices_fn(code)
        except Exception as exc:  # one scrip failing mustn't stop the run
            error = f"{type(exc).__name__}: {exc}"
        symbol = symbol or (quote or {}).get("symbol")
        session = (quote or {}).get("session") or {}
        conn.execute("INSERT INTO snapshots (run_id, scripcode, nse_symbol, session_status, data_as_of, ltp, quote_json, prices_json, error) "
                     "VALUES (?,?,?,?,?,?,?,?,?)",
                     (run, code, symbol, session.get("status"), session.get("data_as_of"), ((quote or {}).get("price") or {}).get("ltp"),
                      json.dumps(quote, default=str) if quote else None, json.dumps(prices, default=str) if prices else None, error))
        line = f"  {code} {symbol or '?'}: " + (error or f"{session.get('status')} ltp {quote['price']['ltp']}")
        if history_fn and symbol:
            have = conn.execute("SELECT COUNT(*) FROM candles WHERE symbol = ? AND source = 'nse'", (symbol,)).fetchone()[0]
            try:
                n = save_candles(conn, symbol, history_fn(symbol, 260 if have < 200 else 25), now)
                line += f"; {n} NSE candles"
            except Exception as exc:
                line += f"; NSE candles failed ({type(exc).__name__}: {str(exc)[:120]})"
        lines.append(line)
    conn.commit()
    return lines


def evaluate(verdict, bars: list) -> dict | None:
    """Outcome of one verdict over the `horizon_days` bars after it, or None until that many have closed."""
    n = verdict["horizon_days"]
    if len(bars) < n:
        return None
    window, entry, side = bars[:n], verdict["entry"], ACTIONS[verdict["action"]]
    ret = window[-1]["close"] / entry - 1
    first_hit = None
    if side and (verdict["stop"] is not None or verdict["target"] is not None):
        first_hit = "neither"
        for b in window:
            stop_hit = verdict["stop"] is not None and (b["low"] <= verdict["stop"] if side > 0 else b["high"] >= verdict["stop"])
            target_hit = verdict["target"] is not None and (b["high"] >= verdict["target"] if side > 0 else b["low"] <= verdict["target"])
            if stop_hit or target_hit:
                # Both inside one daily bar: the candle can't say which came first.
                first_hit = "ambiguous" if stop_hit and target_hit else "stop" if stop_hit else "target"
                break
    hi, lo = max(b["high"] for b in window) / entry - 1, min(b["low"] for b in window) / entry - 1
    return {"first_bar": window[0]["date"], "exit_date": window[-1]["date"], "exit_close": window[-1]["close"],
            "fwd_return": round(ret, 6), "directional_return": round(ret * side, 6) if side else None,
            "max_favourable": round(hi if side >= 0 else -lo, 6), "max_adverse": round(lo if side >= 0 else -hi, 6), "first_hit": first_hit}


def score(conn, now: datetime, history_fn=None) -> list[str]:
    """Score every verdict whose horizon has passed; fetch newer NSE candles first when history_fn is given."""
    pending = conn.execute("SELECT v.* FROM verdicts v LEFT JOIN outcomes o ON o.verdict_id = v.id WHERE o.verdict_id IS NULL "
                           "ORDER BY v.ts").fetchall()
    lines, fetched = [], set()
    for v in pending:
        symbol = v["nse_symbol"]
        if not symbol:
            lines.append(f"  verdict {v['id']}: no NSE symbol, can't score")
            continue
        day = v["ts"][:10]
        if history_fn and symbol not in fetched:
            fetched.add(symbol)
            span = (now.date() - date.fromisoformat(day)).days
            try:
                save_candles(conn, symbol, history_fn(symbol, span * 5 // 7 + 10), now)
            except Exception as exc:
                lines.append(f"  {symbol}: NSE candles failed ({type(exc).__name__}: {str(exc)[:120]})")
        out = evaluate(v, candles(conn, symbol, after=day))
        if out is None:
            have = len(candles(conn, symbol, after=day))
            lines.append(f"  verdict {v['id']} {v['skill']} {symbol}: pending ({have}/{v['horizon_days']} trading days)")
            continue
        conn.execute("INSERT OR REPLACE INTO outcomes (verdict_id, scored_at, horizon_days, first_bar, exit_date, exit_close, fwd_return, "
                     "directional_return, max_favourable, max_adverse, first_hit) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (v["id"], now.isoformat(timespec="seconds"), v["horizon_days"], out["first_bar"], out["exit_date"], out["exit_close"],
                      out["fwd_return"], out["directional_return"], out["max_favourable"], out["max_adverse"], out["first_hit"]))
        lines.append(f"  verdict {v['id']} {v['skill']} {symbol} {v['action']}: {out['fwd_return']:+.2%} by {out['exit_date']}"
                     + (f", {out['first_hit']} first" if out["first_hit"] else ""))
    conn.commit()
    return lines


def report(conn) -> list[dict]:
    """Per skill and version: how its scored verdicts did."""
    rows = conn.execute(
        "SELECT v.skill, v.skill_version, COUNT(*) AS verdicts, COUNT(o.verdict_id) AS scored, "
        "SUM(v.action IN ('buy','sell')) AS directional, "
        "AVG(o.directional_return) AS avg_directional_return, "
        "AVG(CASE WHEN o.directional_return IS NULL THEN NULL WHEN o.directional_return > 0 THEN 1.0 ELSE 0.0 END) AS hit_rate, "
        "SUM(o.first_hit = 'target') AS target_first, SUM(o.first_hit = 'stop') AS stop_first, "
        "SUM(o.first_hit = 'ambiguous') AS ambiguous, AVG(o.fwd_return) AS avg_fwd_return "
        "FROM verdicts v LEFT JOIN outcomes o ON o.verdict_id = v.id GROUP BY v.skill, v.skill_version ORDER BY v.skill").fetchall()
    return [dict(r) for r in rows]


def format_report(rows: list[dict]) -> list[str]:
    if not rows:
        return ["no verdicts yet"]

    def pct(x, signed=True):
        return "-" if x is None else f"{x:+.2%}" if signed else f"{x:.0%}"

    lines = [f"{'skill':34} {'version':12} {'calls':>5} {'scored':>6} {'avg dir ret':>11} {'hit rate':>8}  target/stop/ambiguous first"]
    for r in rows:
        lines.append(f"{r['skill'][:34]:34} {r['skill_version'] or '-':12} {r['verdicts']:>5} {r['scored']:>6} "
                     f"{pct(r['avg_directional_return']):>11} {pct(r['hit_rate'], signed=False):>8}  "
                     f"{r['target_first'] or 0}/{r['stop_first'] or 0}/{r['ambiguous'] or 0}")
    return lines


def read_watchlist(path: Path) -> list[tuple[str, str | None]]:
    """Lines of 'scripcode [NSE symbol]'; '#' starts a comment."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split("#", 1)[0].split()
        if parts:
            out.append((parts[0], parts[1].upper() if len(parts) > 1 else None))
    return out
