"""The tools, as plain functions: no MCP in here, so they can be tested and reused directly.

Every function returns JSON-friendly data and raises ArgError (a bad argument, with what to pass
instead) or bse.BseError (BSE blocked, unreachable, or returned something unexpected).
"""

from __future__ import annotations

import html
import re
import urllib.parse
from datetime import date
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


def detailed_result(code: str, qid: int) -> dict | None:
    """One quarter's P&L, or None when BSE has no filing for that quarter id."""
    data = bse.get("Corp_detailedResult_Transpose_ng", {"Scrip_cd": code, "Qtr": f"{qid:.2f}"})
    rows = data.get("table1") if isinstance(data, dict) else None
    if not rows:
        return None
    meta = {r["fld_desc"]: r.get("Value") for r in rows if r.get("Header") == "2"}
    lines = {r["fld_desc"]: _num(r.get("Value")) for r in rows if r.get("Header") != "2"}
    end = meta.get("Date End", "")
    return {"quarter": label_from_end(end) or quarter_label(qid), "bse_quarter_id": f"{qid:.2f}",
            "period_begin": meta.get("Date Begin"), "period_end": end, "type": meta.get("Type"), "lines": lines}


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
        "price": {"ltp": _num(h.get("LTP") or cur.get("LTP")), "change": _num(cur.get("Chg")), "change_pct": _num(cur.get("PcChg")),
                  "open": _num(h.get("Open")), "high": _num(h.get("High")), "low": _num(h.get("Low")), "prev_close": _num(h.get("PrevClose")),
                  "as_of": h.get("Ason")},
        "range": {"week52_high": hilo.get("Fifty2WkHigh_unadj"), "week52_low": hilo.get("Fifty2WkLow_unadj"),
                  "week_high_low": hilo.get("WeekHighLow"), "month_high_low": hilo.get("MonthHighLow"),
                  "price_band": [band.get("LowerT"), band.get("UpperT")], "circuit_limit": trade.get("CktLimit")},
        "trading": {"wap": _num(trade.get("WAP")), "turnover": unit(trade.get("Turnover"), trade.get("Turnoverin")),
                    "traded_qty": _num(trade.get("TTQ")), "two_week_avg_qty": unit(trade.get("TwoWkAvgQty"), trade.get("TwoWkAvgQtyin")),
                    "delivered_qty": _num(pos.get("DeliverableQty")), "delivery_pct": _num(pos.get("PcDQ_TQ")), "delivery_as_of": pos.get("TradeDate"),
                    "market_cap_cr": _num(trade.get("MktCapFull")), "free_float_mcap_cr": _num(trade.get("MktCapFF")), "ex_date": trade.get("ExDate")},
        "ratios": {"standalone": {k: _num(com.get(k)) for k in ("EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM")},
                   "consolidated": {k: _num(com.get("Con" + k)) for k in ("EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM")}},
        "classification": {k: com.get(k) for k in ("Group", "Index", "Sector", "IndustryNew", "Industry", "IGroup", "ISubGroup", "FaceVal", "SetlType")},
        "flags": {k: h[k] for k in ("ASMText", "GSMText", "EMSText", "SMSText", "IRPText", "DisplayText") if h.get(k)},
    }


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


FINANCIALS_NOTE = ("Amounts as filed with BSE (Rs million unless the company reports otherwise); expenses negative. "
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
