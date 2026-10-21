"""The tools, as plain functions: no MCP in here, so they can be tested and reused directly.

Every function returns JSON-friendly data and raises ArgError (a bad argument, with what to pass
instead) or bse.BseError (BSE blocked, unreachable, or returned something unexpected).
"""

from __future__ import annotations

import html
import re
import urllib.parse
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from . import bse
from .bse import BseError, ENDPOINTS, PDF_BASE

PDF_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.pdf$", re.IGNORECASE)
SEGMENTS = ["Equity", "EQT0", "MF", "HS", "MB", "Preference Shares", "Debentures and Bonds", "Equity - Institutional Series",
            "Commercial Papers", "Government Securities", "Certificate of Deposit", "Treasury Bills"]


class ArgError(ValueError):
    """A tool argument that cannot be right; the message says what to pass instead."""


def _num(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _scaled(value, unit):
    """BSE quotes some quantities as '3.51' with a separate '(Lakh)'; return the plain number, or 'value unit' for a unit we don't know."""
    factor = {"": 1, "(lakh)": 1e5, "(cr.)": 1e7, "(cr)": 1e7}.get(str(unit or "").strip().lower())
    n = _num(value)
    if n is None:
        return None
    return round(n * factor) if factor else f"{value} {unit}".strip()


def _code(scripcode) -> str:
    code = str(scripcode or "").strip()
    if not re.fullmatch(r"\d{5,6}", code):
        raise ArgError(f"scripcode must be the 5-6 digit BSE code (got {scripcode!r}); use search_scrips to find it")
    return code


# ---------------------------------------------------------------- quarters
# BSE numbers result quarters 126 = Jun-25, 127 = Sep-25, ... one per quarter (verified on ABB India).
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def quarter_end(qid: int) -> tuple[int, int]:
    """(year, month index 0-11) of the quarter-end for a BSE quarter id."""
    m = 2025 * 12 + 5 + 3 * (qid - 126)
    return m // 12, m % 12


def fy_label(year: int, month: int) -> str:
    """'Q1 FY27' for a quarter ending in (year, month index). Indian FY runs Apr-Mar."""
    q = {5: 1, 8: 2, 11: 3, 2: 4}.get(month)
    if q is None:
        raise ValueError(f"month index {month} is not a quarter end")
    return f"Q{q} FY{str(year if month <= 2 else year + 1)[-2:]}"


def quarter_label(qid: int) -> str:
    y, m = quarter_end(qid)
    return f"{fy_label(y, m)} ({MONTHS[m]}-{str(y)[-2:]})"


def label_from_end(end: str | None) -> str | None:
    """'30-Jun-26' -> 'Q1 FY27' from BSE's own period-end date; None when it isn't that shape."""
    m = re.fullmatch(r"\d+-(\w{3})-(\d{2})", end or "")
    if not m or m.group(1) not in MONTHS:
        return None
    try:
        return fy_label(2000 + int(m.group(2)), MONTHS.index(m.group(1)))
    except ValueError:
        return None


def last_ended_quarter(today: date | None = None) -> int:
    today = today or _today()
    return 126 + (today.year * 12 + today.month - 2 - (2025 * 12 + 5)) // 3


def quarter_id_for(label: str) -> int:
    """'Q1 FY27' -> 130. Also accepts a bare BSE id like '130' or '130.00'."""
    text = str(label).strip().upper()
    if re.fullmatch(r"\d{3}(\.\d+)?", text):
        return int(float(text))
    m = re.fullmatch(r"Q([1-4])\s*FY\s*(\d{2}|\d{4})", text)
    if not m:
        raise ArgError(f"quarter must look like 'Q1 FY27' (got {label!r})")
    q, fy = int(m.group(1)), int(m.group(2))
    fy = fy if fy > 100 else 2000 + fy
    month = {1: 5, 2: 8, 3: 11, 4: 2}[q]
    year = fy - 1 if q < 4 else fy
    return 126 + ((year * 12 + month) - (2025 * 12 + 5)) // 3


LINE = {"sales": "Net Sales/Revenue From Operations", "cmc": "Cost of Materials Consumed", "purch": "Purchases of stock-in-trade",
        "inv": "Changes in inventories of finished goods, work-in-progress and stock-in-trade", "emp": "Employee benefit expense",
        "oth": "Other Expenses", "pbt": "Profit (+)/ Loss (-) from Ordinary Activities before Tax", "tax": "Tax",
        "pat": "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax"}


def derived(lines: dict) -> dict:
    """EBITDA and margins from BSE's lines; a metric is None when any input line is missing."""
    g = lines.get
    parts = [g(LINE[k]) for k in ("sales", "cmc", "purch", "inv", "emp", "oth")]
    ebitda = round(sum(parts), 2) if all(p is not None for p in parts) else None
    sales, pbt, tax, pat = g(LINE["sales"]), g(LINE["pbt"]), g(LINE["tax"]), g(LINE["pat"])

    def pct(a, b):
        return round(a / b, 4) if a is not None and b else None

    return {"ebitda": ebitda, "ebitda_margin": pct(ebitda, sales), "pbt_margin": pct(pbt, sales),
            "tax_rate": pct(-tax if tax is not None else None, pbt), "pat_margin": pct(pat, sales)}


def period_label(begin: str | None, end: str | None) -> str | None:
    """'01-Apr-26', '30-Jun-26' -> 'Apr–Jun 2026': the months the figures cover, whatever the company's FY."""
    rx = r"\d+-(\w{3})-(\d{2})"
    b, e = re.fullmatch(rx, begin or ""), re.fullmatch(rx, end or "")
    if not b or not e or b.group(1) not in MONTHS or e.group(1) not in MONTHS:
        return None
    by, ey = 2000 + int(b.group(2)), 2000 + int(e.group(2))
    return f"{b.group(1)}–{e.group(1)} {ey}" if by == ey else f"{b.group(1)} {by}–{e.group(1)} {ey}"


def detailed_result(code: str, qid: int) -> dict | None:
    """One quarter's P&L, or None when BSE has no filing for that quarter id."""
    data = bse.get("Corp_detailedResult_Transpose_ng", {"Scrip_cd": code, "Qtr": f"{qid:.2f}"})
    rows = data.get("table1") if isinstance(data, dict) else None
    if not rows:
        return None
    meta = {r["fld_desc"]: r.get("Value") for r in rows if r.get("Header") == "2"}
    lines = {r["fld_desc"]: _num(r.get("Value")) for r in rows if r.get("Header") != "2"}
    if not any(v is not None for v in lines.values()):
        return None  # BSE answers a quarter that isn't filed yet with empty meta rows only
    begin, end = meta.get("Date Begin", ""), meta.get("Date End", "")
    return {"quarter": label_from_end(end) or quarter_label(qid), "period": period_label(begin, end),
            "bse_quarter_id": f"{qid:.2f}", "period_begin": begin, "period_end": end, "type": meta.get("Type"), "lines": lines}


# ---------------------------------------------------------------- session status
# BSE answers a quote for any scrip at any time, with the last price it has: after hours, on a holiday,
# and for a suspended scrip years after its last trade. The only thing that says how old the price is
# is the quote's own 'Ason' stamp, so "is this live?" means "is that stamp today?".
IST = timezone(timedelta(hours=5, minutes=30))
OPEN_AT, CLOSE_AT = time(9, 15), time(15, 30)
REFERENCE_SCRIPS = ("500325", "500180")  # Reliance, HDFC Bank: if neither traded today, the market didn't open


def _now() -> datetime:  # separate so tests can pin the clock
    return datetime.now(IST)


def parse_as_of(stamp: str | None) -> datetime | None:
    """'21 Oct 26 | 13:23' -> that moment in IST; None when BSE's stamp isn't that shape."""
    try:
        return datetime.strptime(re.sub(r"\s+", " ", str(stamp)).strip(), "%d %b %y | %H:%M").replace(tzinfo=IST)
    except ValueError:
        return None


def session_status(stock_as_of: str | None, reference_as_of: list[str | None], now: datetime | None = None) -> dict:
    """Whether a scrip's price is from today's session, and if not, why.

    reference_as_of: the stamps of the reference scrips, only looked at when the stock's own is not from today
    (pass [] when there was no need to fetch them)."""
    now = (now or _now()).astimezone(IST)
    stamp = parse_as_of(stock_as_of)
    out = {"status": "unknown", "data_as_of": stamp.isoformat(timespec="minutes") if stamp else stock_as_of,
           "checked_at": now.isoformat(timespec="minutes")}
    if stamp is None:
        out["note"] = f"couldn't read BSE's price timestamp ({stock_as_of!r}); treat the price as possibly stale"
    elif stamp.date() == now.date():
        out["status"] = "pre_open" if now.time() < OPEN_AT else "live" if now.time() < CLOSE_AT else "closed_after_session"
        out["note"] = {"pre_open": "priced today but the continuous session hasn't started (opens 09:15 IST)",
                       "live": "priced today, session in progress: today's candle is incomplete",
                       "closed_after_session": "today's session has ended: this is today's close"}[out["status"]]
    else:
        refs = [parse_as_of(r) for r in reference_as_of]
        if any(r and r.date() == now.date() for r in refs):
            out["status"] = "stock_not_trading"
            out["note"] = (f"the market traded today but this scrip's last price is from {stamp.date().isoformat()}: suspended, "
                           "halted, or no trades today. Its numbers are not live")
        elif refs and all(r is None for r in refs):
            out["note"] = "this scrip's price is not from today and the reference scrips couldn't be read, so market state is unknown"
        elif now.weekday() < 5 and now.time() < OPEN_AT:
            out["status"] = "awaiting_open"
            out["note"] = f"no trades yet today (before 09:15 IST, or a holiday); latest price is from {stamp.date().isoformat()}"
        else:
            out["status"] = "market_closed"
            out["note"] = f"no scrip has traded today (weekend or holiday); latest price is from {stamp.date().isoformat()}"
    return out


def _stamp(code: str) -> str | None:
    head = bse.get("getScripHeaderData", {"Debtflag": "", "scripcode": code, "seriesid": ""})
    return (head.get("Header") or {}).get("Ason") if isinstance(head, dict) else None


def _session_for(code: str, stock_as_of: str | None) -> dict:
    """session_status for a scrip, fetching the reference scrips' stamps only when its own isn't from today."""
    now = _now()
    stamp = parse_as_of(stock_as_of)
    refs: list[str | None] = []
    if stamp is not None and stamp.date() != now.date():
        for ref in (r for r in REFERENCE_SCRIPS if r != code):
            try:
                refs.append(_stamp(ref))
            except BseError:
                refs.append(None)
            if (p := parse_as_of(refs[-1])) and p.date() == now.date():
                break  # one scrip that traded today is proof enough
    return session_status(stock_as_of, refs, now)


def plain(text: str) -> str:
    """BSE headlines carry <BR> and entities; keep the line breaks, drop the rest."""
    text = re.sub(r"<\s*br\s*/?>", "\n", text or "", flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


# ---------------------------------------------------------------- tools
def search_scrips(query: str) -> list[dict]:
    rows = bse.get("GetQuoteAllSearchDatabeta", {"searchString": str(query or "").strip()})
    if not isinstance(rows, list):
        raise BseError(f"unexpected search reply: {str(rows)[:200]}")
    seen, out = set(), []
    for r in rows:
        key = (r.get("strSricpCode"), r.get("Type"))
        if key in seen:
            continue
        seen.add(key)
        out.append({"scripcode": r.get("strSricpCode"), "symbol": r.get("shortName"), "name": r.get("scripName"),
                    "isin": r.get("Isin"), "market": (r.get("Type") or "").strip()})
    return out[:20]


def get_quote(scripcode: str) -> dict:
    code = _code(scripcode)
    head = bse.get("getScripHeaderData", {"Debtflag": "", "scripcode": code, "seriesid": ""})
    com = bse.get("ComHeadernew_par", {"quotetype": "", "scripcode": code, "seriesid": ""})
    trade = bse.get("StockTrading", {"flag": "", "quotetype": "EQ", "scripcode": code})
    hilo = bse.get("HighLow", {"Type": "EQ", "flag": "C", "scripcode": code})
    pos = bse.get("SecurityPosition", {"scripcode": code})
    band = bse.get("PriceBand", {"scripcode": code, "seriesid": ""})
    h, cur, cmp_ = head.get("Header") or {}, head.get("CurrRate") or {}, head.get("Cmpname") or {}
    if not cmp_.get("FullN") and not com.get("SecurityId"):
        raise BseError(f"BSE has no equity scrip {code}; check the code with search_scrips")
    unit = lambda v, u: f"{v} {u or ''}".strip() if v else None  # noqa: E731
    return {
        "scripcode": code, "name": cmp_.get("FullN"), "symbol": com.get("SecurityId"), "isin": com.get("ISIN"),
        "bse_url": bse.SITE + cmp_["SEOUrlEQ"] if cmp_.get("SEOUrlEQ") else None,
        "session": _session_for(code, h.get("Ason")),
        "price": {"ltp": _num(h.get("LTP") or cur.get("LTP")), "change": _num(cur.get("Chg")), "change_pct": _num(cur.get("PcChg")),
                  "open": _num(h.get("Open")), "high": _num(h.get("High")), "low": _num(h.get("Low")), "prev_close": _num(h.get("PrevClose")),
                  "as_of": h.get("Ason")},
        "range": {"week52_high": hilo.get("Fifty2WkHigh_unadj"), "week52_low": hilo.get("Fifty2WkLow_unadj"),
                  "week_high_low": hilo.get("WeekHighLow"), "month_high_low": hilo.get("MonthHighLow"),
                  "price_band": [band.get("LowerT"), band.get("UpperT")], "circuit_limit": trade.get("CktLimit")},
        "trading": {"wap": _num(trade.get("WAP")), "turnover": unit(trade.get("Turnover"), trade.get("Turnoverin")),
                    "traded_qty": _scaled(trade.get("TTQ"), trade.get("TTQin")), "two_week_avg_qty": unit(trade.get("TwoWkAvgQty"), trade.get("TwoWkAvgQtyin")),
                    "delivered_qty": _num(pos.get("DeliverableQty")), "delivery_pct": _num(pos.get("PcDQ_TQ")), "delivery_as_of": pos.get("TradeDate"),
                    "market_cap_cr": _num(trade.get("MktCapFull")), "free_float_mcap_cr": _num(trade.get("MktCapFF")), "ex_date": trade.get("ExDate")},
        "ratios": {"standalone": {k: _num(com.get(k)) for k in ("EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM")},
                   "consolidated": {k: _num(com.get("Con" + k)) for k in ("EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM")}},
        "classification": {k: com.get(k) for k in ("Group", "Index", "Sector", "IndustryNew", "Industry", "IGroup", "ISubGroup", "FaceVal", "SetlType")},
        "flags": {k: h[k] for k in ("ASMText", "GSMText", "EMSText", "SMSText", "IRPText", "DisplayText") if h.get(k)},
    }


def get_session_status(scripcode: str) -> dict:
    code = _code(scripcode)
    return {"scripcode": code, **_session_for(code, _stamp(code))}


def get_market_depth(scripcode: str) -> dict:
    code = _code(scripcode)
    d = bse.get("MarketDepth", {"flag": "", "quotetype": "EQ", "scripcode": code})
    return {"scripcode": code, "as_of": d.get("dttm"),
            "bids": [{"price": _num(d.get(f"BPrice{i}")), "qty": _num(d.get(f"BQty{i}"))} for i in range(1, 6)],
            "asks": [{"price": _num(d.get(f"SPrice{i}")), "qty": _num(d.get(f"SQty{i}"))} for i in range(1, 6)],
            "total_bid_qty": _num(d.get("TotalBQty")), "total_ask_qty": _num(d.get("TotalSQty"))}


def get_peers(scripcode: str) -> list[dict]:
    code = _code(scripcode)
    d = bse.get("EQPeerGp", {"scripcomare": "", "scripcode": code})
    rows = d.get("Table") if isinstance(d, dict) else None
    if not rows:
        raise BseError(f"BSE returned no peer table for {code}")
    keys = ["Name", "scrip_cd", "LTP", "Change", "PE", "PB", "EPS", "Revenue", "PAT", "OPM", "NPM", "w52hi", "w52lo", "Results_QuarterName"]
    return [{k: r.get(k) for k in keys} for r in rows]


FINANCIALS_NOTE = ("'quarter' names the quarter in the Indian April-March financial year; 'period' gives the months the figures "
                   "cover, which is what to use for companies with another financial year (ABB India, for one, reports Jan-Dec). "
                   "Amounts as filed with BSE (Rs million unless the company reports otherwise); expenses negative. "
                   "derived.* are computed here: ebitda = sales + materials + stock-in-trade purchases + inventory change + employee + other expenses.")


def get_financials(scripcode: str, quarters: int = 5, upto: str | None = None) -> dict:
    code = _code(scripcode)
    n = max(1, min(16, int(quarters)))
    if upto:
        latest = quarter_id_for(upto)
    else:
        # The results tab links to the latest quarter; probe one ahead and a few behind in case that link lags.
        tab = bse.get("TabResults_PAR_RESULTS", {"scripcode": code, "tabtype": "RESULTS"})
        link = ((tab.get("resultinS") or [{}])[0].get("LLQ") or "") if isinstance(tab, dict) else ""
        m = re.search(r"qtr=([\d.]+)", link)
        base = int(float(m.group(1))) if m else last_ended_quarter()
        latest = next((q for q in (base + 1, base, base - 1, base - 2, base - 3) if detailed_result(code, q)), None)
        if latest is None:
            raise BseError(f"BSE has no quarterly results for {code} around {quarter_label(base)}")
    out, misses, qid = [], 0, latest
    while len(out) < n and misses < 4:
        r = detailed_result(code, qid)
        qid -= 1
        if r is None:
            misses += 1
            continue
        misses = 0
        r["derived"] = derived(r["lines"])
        out.append(r)
    return {"scripcode": code, "quarters": out, "note": FINANCIALS_NOTE}


def _today() -> date:  # separate so tests can pin the date
    return date.today()


def get_announcements(scripcode: str, months: int = 12, category: str = "all", page: int = 1) -> dict:
    code = _code(scripcode)
    months = max(1, min(12, int(months)))
    if category not in ("all", "results"):
        raise ArgError("category must be 'all' or 'results'")
    today = _today()
    y, m = today.year, today.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    since = date(y, m, min(today.day, 28))
    cat, sub = ("Result", "Financial Results") if category == "results" else ("-1", "-1")
    d = bse.get("AnnSubCategoryGetData", {"strCat": cat, "strPrevDate": since.strftime("%Y%m%d"), "strScrip": code, "strSearch": "P",
                                          "strToDate": today.strftime("%Y%m%d"), "strType": "C", "subcategory": sub, "pageno": str(max(1, int(page)))})
    rows = d.get("Table") or []
    total = _num(((d.get("Table1") or [{}])[0]).get("ROWCNT"))
    items = []
    for r in rows:
        att = (r.get("ATTACHMENTNAME") or "").strip()
        items.append({"date": r.get("NEWS_DT") or r.get("DT_TM"), "headline": plain(r.get("HEADLINE") or r.get("NEWSSUB") or ""),
                      "category": r.get("CATEGORYNAME"), "subcategory": r.get("SUBCATNAME"), "attachment": att or None,
                      "pdf_url": PDF_BASE + urllib.parse.quote(att) if att else None})
    return {"scripcode": code, "from": since.isoformat(), "to": today.isoformat(), "page": page,
            "total": int(total) if total is not None else len(items), "announcements": items}


def download_announcement_pdf(attachment: str, save_dir: str, filename: str | None = None) -> str:
    if not PDF_NAME.match(attachment or ""):
        raise ArgError(f"not a BSE attachment name: {attachment!r} (use the 'attachment' field from get_announcements)")
    status, body = bse.fetch(PDF_BASE + attachment)
    if status != 200 or not body.startswith(b"%PDF"):
        raise BseError(f"could not fetch {attachment}: HTTP {status}")
    name = re.sub(r"[^A-Za-z0-9 ._()&-]", "_", filename or attachment).strip() or attachment
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    target = Path(save_dir).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    path.write_bytes(body)
    return str(path)


def list_scrips(segment: str = "Equity", status: str = "Active", group: str = "", name_contains: str = "",
                scripcode: str = "", limit: int = 200) -> dict:
    if segment not in SEGMENTS:
        raise ArgError(f"segment must be one of {SEGMENTS}")
    rows = bse.get("ListofScripData_new", {"Group": group, "Scripcode": str(scripcode).strip(), "segment": segment, "status": status,
                                            "scripName": str(name_contains).strip()})
    if not isinstance(rows, list):
        raise BseError(f"unexpected list reply: {str(rows)[:200]}")
    n = max(1, int(limit))
    keys = ["SCRIP_CD", "scrip_id", "Scrip_Name", "Issuer_Name", "Segment", "Status", "GROUP", "FACE_VALUE", "ISIN_NUMBER", "Mktcap"]
    return {"total": len(rows), "returned": min(len(rows), n), "rows": [{k: r.get(k) for k in keys} for r in rows[:n]]}


def call_bse_api(endpoint: str, params: dict | None = None, scripcode: str = "", quarter: str = ""):
    if endpoint not in ENDPOINTS:
        raise ArgError(f"unknown endpoint {endpoint!r}; one of: {', '.join(ENDPOINTS)}")
    qid = f"{quarter_id_for(quarter):.2f}" if quarter else ""
    filled = {k: v.replace("{scripcode}", str(scripcode).strip()).replace("{quarter}", qid) for k, v in ENDPOINTS[endpoint][2].items()}
    filled.update({k: str(v) for k, v in (params or {}).items()})
    return bse.get(endpoint, filled)


# ---------------------------------------------------------------- analysis
def analyze_fundamentals(scripcode: str, quarters: int = 8) -> dict:
    from . import analysis

    code = _code(scripcode)
    n = max(1, min(16, int(quarters)))
    fin = get_financials(code, quarters=n)
    qs = fin["quarters"]
    if not qs:
        raise BseError(f"BSE returned no quarterly results for {code}")
    out = analysis.fundamentals(qs)
    head = bse.get("getScripHeaderData", {"Debtflag": "", "scripcode": code, "seriesid": ""})
    trade = bse.get("StockTrading", {"flag": "", "quotetype": "EQ", "scripcode": code})
    card = bse.get("TabResults_PAR_RESULTS", {"scripcode": code, "tabtype": "RESULTS"})
    h, cur = head.get("Header") or {}, head.get("CurrRate") or {}
    price = _num(h.get("LTP") or cur.get("LTP"))
    latest = out["quarters"][0] if out["quarters"] else None
    unit = analysis.unit_factor(latest["metrics"]["revenue"] if latest else None, card if isinstance(card, dict) else None,
                                latest["period_end"] if latest else None)
    out["valuation"] = analysis.valuation(out["ttm"], price, _num(trade.get("MktCapFull")), unit["crore_per_unit"])
    com = bse.get("ComHeadernew_par", {"quotetype": "", "scripcode": code, "seriesid": ""})
    out["valuation"]["bse_reported"] = {"pe": _num(com.get("PE")), "eps": _num(com.get("EPS")),
                                        "note": "BSE's own P/E and EPS; their EPS basis (e.g. annual, including discontinued items) can differ from TTM continuing EPS"}
    return {"scripcode": code, "session": _session_for(code, h.get("Ason")), "unit": unit, **out, "definitions": analysis.definitions_for(out["kind"]),
            "note": "Figures are standalone as filed with BSE; amounts in the filed unit (see 'unit') unless the key ends in _cr. "
                    "Further reading on these ratios: Zerodha Varsity, Fundamental Analysis https://zerodha.com/varsity/module/fundamental-analysis/"}


def get_price_history(scripcode: str) -> dict:
    """BSE's daily closes and traded quantity for the last 12 months (the 12M view of the price chart)."""
    code = _code(scripcode)
    d = bse.get("StockReachGraphCas", {"flag": "12M", "fromdate": "", "scripcode": code, "seriesid": "", "todate": ""})
    rows = d.get("Data") if isinstance(d, dict) else None
    if not isinstance(rows, list) or not rows:
        raise BseError(f"BSE returned no price history for {code}")
    dates, closes, volumes = [], [], []
    for r in rows:
        price = _num(r.get("vale1") or r.get("vale0"))
        try:
            day = datetime.strptime(str(r.get("dttm", ""))[4:15], "%b %d %Y").date().isoformat()  # 'Tue Oct 21 2025 00:00:00'
        except ValueError:
            day = None
        if price is None or day is None:
            raise BseError(f"unexpected price-history row from BSE: {str(r)[:200]}")
        dates.append(day), closes.append(price), volumes.append(_num(r.get("vole")) or 0.0)
    if any(b <= a for a, b in zip(dates, dates[1:])):
        raise BseError(f"BSE's price history for {code} is not in date order")
    return {"scripcode": code, "symbol": d.get("Scripname"), "bars": len(dates), "from": dates[0], "to": dates[-1],
            "dates": dates, "closes": closes, "volumes": volumes,
            "note": "Daily closes and traded quantity on BSE, oldest first, from BSE's 12-month price chart. There are no daily "
                    "open, high or low figures here, and the quantities are BSE's alone (NSE usually trades more). To compute "
                    "indicators, call analyze_prices with this scripcode rather than copying the numbers."}


def analyze_prices(closes: list[float] | None = None, dates: list[str] | None = None, highs: list[float] | None = None,
                   lows: list[float] | None = None, volumes: list[float] | None = None, timeframe: str = "daily",
                   entry_date: str | None = None, side: str = "long", scripcode: str | None = None) -> dict:
    from . import analysis

    if scripcode:
        if any(v is not None for v in (closes, dates, highs, lows, volumes)):
            raise ArgError("pass either scripcode (BSE's daily closes for the last 12 months) or your own series, not both")
        hist = get_price_history(scripcode)
        try:
            session = _session_for(hist["scripcode"], _stamp(hist["scripcode"]))
        except BseError:
            session = session_status(None, [])
        closes, dates, volumes = hist["closes"], hist["dates"], hist["volumes"]
        source = (f"BSE's daily closes and volumes for {hist['scripcode']}, {hist['from']} to {hist['to']}. BSE gives no daily highs "
                  "and lows here, so ATR, ADX, stochastic, chandelier and pivots need daily candles from another source.")
    elif closes is None:
        raise ArgError("pass closes (oldest first), or scripcode to use BSE's daily closes for the last 12 months")
    else:
        source = "the series passed in, oldest first"
    try:
        out = analysis.technicals(closes, dates, highs, lows, volumes, timeframe, entry_date, side)
    except ValueError as exc:
        raise ArgError(str(exc)) from None
    out["source"] = source
    if scripcode:
        out["session"] = session
    out["definitions"] = analysis.TECHNICAL_DEFINITIONS
    out["note"] = ("Indicators describe past prices; they are not forecasts or advice. "
                   "Further reading: Zerodha Varsity, Technical Analysis https://zerodha.com/varsity/module/technical-analysis/")
    return out


def position_size(capital: float, entry: float, stop: float | None = None, side: str = "long", risk_pct: float = 1.0,
                  atr: float | None = None, atr_multiplier: float = 2.0, target: float | None = None, leverage: float = 1.0,
                  max_position_pct: float = 20.0, win_rate: float | None = None, avg_win_loss: float | None = None,
                  segment: str = "delivery", exchange: str = "NSE", brokerage_per_order: float = 0.0,
                  brokerage_pct: float = 0.0, dp_charge: float = 0.0, exchange_txn_rate: float | None = None) -> dict:
    from . import sizing

    try:
        out = sizing.position_size(capital, entry, stop, side, risk_pct, atr, atr_multiplier, target, leverage, max_position_pct,
                                   win_rate, avg_win_loss, segment, exchange, brokerage_per_order, brokerage_pct, dp_charge,
                                   exchange_txn_rate)
    except sizing.SizingError as exc:
        raise ArgError(str(exc)) from None
    out["note"] = "Arithmetic on the inputs given, not a recommendation to trade."
    return out


# ---------------------------------------------------------------- journal
def record_analysis(scripcode: str, skill: str, action: str, entry: float | None = None, stop: float | None = None,
                    target: float | None = None, horizon_days: int = 20, confidence: float | None = None, rationale: str = "",
                    model: str | None = None, nse_symbol: str | None = None) -> dict:
    from . import journal

    code = _code(scripcode)
    action = str(action or "").strip().lower()
    if action not in journal.ACTIONS:
        raise ArgError(f"action must be one of {', '.join(journal.ACTIONS)} (sell = bearish: short, or exit a long)")
    skill = str(skill or "").strip()
    if not skill:
        raise ArgError("skill: the skill that produced this verdict, e.g. 'bse-mcp-trading-toolkit'")
    horizon = int(horizon_days)
    if not 1 <= horizon <= 250:
        raise ArgError("horizon_days: trading days to judge the call over, 1-250 (20 is about a month)")
    if confidence is not None and not 0 <= confidence <= 1:
        raise ArgError("confidence is a fraction between 0 and 1")
    quote = get_quote(code)
    price = entry if entry is not None else quote["price"]["ltp"]
    if not price or price <= 0:
        raise ArgError("no entry given and BSE has no price for this scrip")
    side = journal.ACTIONS[action]
    if side:  # buy: stop below, target above the entry; sell: the other way round
        if stop is not None and side * (price - stop) <= 0:
            raise ArgError(f"for a {action} the stop must be {'below' if side > 0 else 'above'} the entry ({price})")
        if target is not None and side * (target - price) <= 0:
            raise ArgError(f"for a {action} the target must be {'above' if side > 0 else 'below'} the entry ({price})")
    now = _now()
    with journal.connect() as conn:
        vid = journal.record(conn, scripcode=code, skill=skill, action=action, entry=price, quote=quote, now=now, stop=stop, target=target,
                             horizon_days=horizon, confidence=confidence, rationale=str(rationale or ""), model=model,
                             nse_symbol=(nse_symbol or "").strip().upper() or None)
    return {"id": vid, "journal": str(journal.db_path()), "scripcode": code, "skill": skill, "action": action, "entry": price,
            "stop": stop, "target": target, "horizon_days": horizon, "session": quote["session"],
            "note": f"Scored by `bse-mcp score` once {horizon} trading days have closed after today, against NSE daily candles."}
