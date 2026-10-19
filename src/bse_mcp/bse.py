"""Talking to BSE India's public website APIs.

BSE's CDN (Akamai) answers 403 to requests that don't look like a browser on bseindia.com,
and no endpoint sends CORS headers. So every call goes out with the headers Chrome sends from
the site, and, when curl_cffi is installed, with Chrome's TLS fingerprint too. Strategies are
tried least-blockable first; the first one BSE doesn't refuse wins.
"""

from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import zlib

try:  # Optional: impersonates Chrome's TLS fingerprint, which BSE's CDN checks.
    from curl_cffi import requests as curl_requests
except ImportError:  # pragma: no cover - depends on the environment
    curl_requests = None

SITE = "https://www.bseindia.com"
PDF_BASE = SITE + "/xml-data/corpfiling/AttachHis/"
WARMUP_URL = SITE + "/corporates/ann.html"  # a visit sets the cookies Akamai expects on API calls

BASES = {
    "api": "https://api.bseindia.com/BseIndiaAPI/api",
    "realtime": "https://api.bseindia.com/RealTimeBseIndiaAPI/api",
    "msource": "https://api.bseindia.com/MSource/1D",
}

# name -> (base, path, default params). {scripcode} and {quarter} are filled in by call_bse_api;
# the other tools build their own params. The same table lives in worker/worker.js.
ENDPOINTS = {
    "getScripHeaderData": ("api", "getScripHeaderData/w", {"Debtflag": "", "scripcode": "{scripcode}", "seriesid": ""}),
    "ComHeadernew_par": ("api", "ComHeadernew_par/w", {"quotetype": "", "scripcode": "{scripcode}", "seriesid": ""}),
    "MarketDepth": ("realtime", "MarketDepth/w", {"flag": "", "quotetype": "EQ", "scripcode": "{scripcode}"}),
    "StockTrading": ("api", "StockTrading/w", {"flag": "", "quotetype": "EQ", "scripcode": "{scripcode}"}),
    "HighLow": ("api", "HighLow/w", {"Type": "EQ", "flag": "C", "scripcode": "{scripcode}"}),
    "PriceBand": ("api", "PriceBand/w", {"scripcode": "{scripcode}", "seriesid": ""}),
    "SecurityPosition": ("api", "SecurityPosition/w", {"scripcode": "{scripcode}"}),
    "StockReachGraphCas": ("api", "StockReachGraphCas/w", {"flag": "0", "fromdate": "", "scripcode": "{scripcode}", "seriesid": "", "todate": ""}),
    "EQPeerGp": ("api", "EQPeerGp/w", {"scripcomare": "", "scripcode": "{scripcode}"}),
    "TabResults_PAR_NEWS": ("api", "TabResults_PAR/w", {"scripcode": "{scripcode}", "tabtype": "NEWS"}),
    "TabResults_PAR_RESULTS": ("api", "TabResults_PAR/w", {"scripcode": "{scripcode}", "tabtype": "RESULTS"}),
    "ScripwiseCautionaryMsg": ("api", "ScripwiseCautionaryMsg/w", {"scripcode": "{scripcode}"}),
    "LeftMenunew": ("api", "LeftMenunew/w", {"scripcode": "{scripcode}"}),
    "Corp_detailedResult_Transpose_ng": ("api", "Corp_detailedResult_Transpose_ng/w", {"Scrip_cd": "{scripcode}", "Qtr": "{quarter}"}),
    "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng": ("api", "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng/w", {"Scrip_cd": "{scripcode}", "QuarterID": "{quarter}"}),
    "Corp_SEGMENTS_QUART_COMP_ng": ("api", "Corp_SEGMENTS_QUART_COMP_ng/w", {"Scrip_cd": "{scripcode}", "QuarterID": "{quarter}"}),
    "Corp_Segments_Total_p_ng": ("api", "Corp_Segments_Total_p_ng/w", {"Scrip_cd": "{scripcode}", "QuarterID": "{quarter}"}),
    "Corp_GET_BSEDnBResultNotes_ng": ("api", "Corp_GET_BSEDnBResultNotes_ng/w", {"scrip_cd": "{scripcode}", "currQtr": "{quarter}"}),
    "AnnSubCategoryGetData": ("api", "AnnSubCategoryGetData/w", {"strCat": "-1", "strPrevDate": "", "strScrip": "{scripcode}", "strSearch": "P", "strToDate": "", "strType": "C", "subcategory": "-1", "pageno": "1"}),
    "GetQuoteAllSearchDatabeta": ("msource", "GetQuoteAllSearchDatabeta.aspx", {"searchString": "{scripcode}"}),
    "ListofScripData_new": ("api", "ListofScripData_new/w", {"Group": "", "Scripcode": "", "segment": "Equity", "status": "Active", "scripName": ""}),
    "ddlGroup": ("api", "ddlGroup/w", {"flag": "0"}),
    "Mkt_GetTicker_ng": ("api", "Mkt_GetTicker_ng/w", {"env": "1"}),
}

# Everything Chrome sends on bseindia.com's own call to these APIs.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Origin": SITE,
    "Referer": SITE + "/",
    "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"macOS"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
}
# With curl_cffi, its Chrome impersonation sets the User-Agent and sec-ch-* headers itself so
# they match the TLS fingerprint; only add what the site adds.
IMPERSONATE_HEADERS = {"Accept": BROWSER_HEADERS["Accept"], "Origin": SITE, "Referer": SITE + "/"}


class BseError(Exception):
    """BSE did not give a usable answer (blocked, unreachable, not JSON)."""


def _decode(body: bytes, encoding: str | None) -> bytes:
    encoding = (encoding or "").lower()
    if encoding == "gzip":
        return gzip.decompress(body)
    if encoding == "deflate":
        return zlib.decompress(body)
    return body


def _via_urllib(url: str):
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, _decode(resp.read(), resp.headers.get("Content-Encoding"))
    except urllib.error.HTTPError as exc:
        return exc.code, _decode(exc.read(), exc.headers.get("Content-Encoding"))


def _via_curl(url: str):
    """The system curl has a different TLS fingerprint that BSE sometimes accepts."""
    cmd = ["curl", "-sS", "--compressed", "-m", "20", "-w", "\n%{http_code}"]
    for key, value in BROWSER_HEADERS.items():
        if key != "Accept-Encoding":
            cmd += ["-H", f"{key}: {value}"]
    try:
        out = subprocess.run(cmd + [url], capture_output=True, timeout=30, check=True).stdout
    except subprocess.CalledProcessError as exc:
        raise BseError(f"curl exit {exc.returncode}: {exc.stderr.decode('utf-8', 'replace').strip()[:200]}") from None
    body, _, status = out.rpartition(b"\n")
    return int(status), body


_session = None


def _via_curl_cffi(url: str, warm_up: bool):
    """Chrome TLS/HTTP2 impersonation; optionally visit bseindia.com first for cookies."""
    global _session
    if _session is None or warm_up:
        _session = curl_requests.Session(impersonate="chrome")
    if warm_up:
        _session.get(WARMUP_URL, timeout=20)
    resp = _session.get(url, headers=IMPERSONATE_HEADERS, timeout=20)
    return resp.status_code, resp.content


def strategies():
    """(name, fetch) pairs, least-blockable first."""
    found = []
    if curl_requests is not None:
        found.append(("curl_cffi", lambda url: _via_curl_cffi(url, warm_up=False)))
        found.append(("curl_cffi+cookies", lambda url: _via_curl_cffi(url, warm_up=True)))
    found.append(("urllib", _via_urllib))
    if shutil.which("curl"):
        found.append(("curl", _via_curl))
    return found


def fetch(url: str) -> tuple[int, bytes]:
    """(status, body) from the first strategy BSE doesn't refuse. Raises BseError if none could connect."""
    errors = []
    status, body = 403, b""
    for name, fn in strategies():
        try:
            status, body = fn(url)
        except Exception as exc:  # network errors from any of the clients
            errors.append(f"{name}: {str(exc)[:120]}")
            continue
        if status != 403:
            return status, body
    if status == 403:
        return status, body
    raise BseError("Could not reach BSE: " + "; ".join(errors))


def unwrap(value):
    """BSE sometimes returns JSON inside a JSON string; decode those wherever they appear."""
    if isinstance(value, str):
        text = value.strip()
        if (text[:1] == "{" and text.endswith("}")) or (text[:1] == "[" and text.endswith("]")):
            try:
                return unwrap(json.loads(text))
            except ValueError:
                return value
        return value
    if isinstance(value, list):
        return [unwrap(v) for v in value]
    if isinstance(value, dict):
        return {k: unwrap(v) for k, v in value.items()}
    return value


def url_for(name: str, params: dict) -> str:
    base, path, _ = ENDPOINTS[name]
    return f"{BASES[base]}/{path}?{urllib.parse.urlencode(params)}"


def get(name: str, params: dict):
    """Call one BSE endpoint by registry name and return its decoded JSON."""
    status, body = fetch(url_for(name, params))
    text = body.decode("utf-8", "replace")
    if status == 403:
        hint = ("" if curl_requests else " Install curl_cffi (pip install curl_cffi) so requests carry Chrome's TLS fingerprint,"
                " or") + " run  bse-mcp --diag  to see which client BSE accepts from this network."
        raise BseError(f"BSE refused {name} (HTTP 403).{hint}")
    if status != 200:
        raise BseError(f"{name} failed: HTTP {status}: {text[:200]}")
    try:
        return unwrap(json.loads(text))
    except ValueError:
        raise BseError(f"{name} did not return JSON: {text[:200]}") from None


def diagnose(url: str | None = None) -> str:
    """Try every strategy against BSE and describe what came back (the --diag command)."""
    url = url or url_for("getScripHeaderData", {"Debtflag": "", "scripcode": "500002", "seriesid": ""})
    lines = [f"URL: {url}", f"curl_cffi installed: {curl_requests is not None}"]
    for name, fn in strategies():
        try:
            status, body = fn(url)
        except Exception as exc:
            lines.append(f"{name:18} error: {str(exc)[:160]}")
            continue
        lines.append(f"{name:18} HTTP {status}: {body[:120].decode('utf-8', 'replace')!r}")
    return "\n".join(lines)
