"""Serve BSE answers from fixtures instead of the network, for every test."""
import json
import urllib.parse

import pytest

from bse_mcp import bse, tools

from . import fixtures as F


class FakeBse:
    """Stands in for bse.fetch: answers from fixtures, records every call, can refuse named endpoints."""

    def __init__(self):
        self.calls = []
        self.refuse = set()

    def __call__(self, url):
        u = urllib.parse.urlparse(url)
        q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
        if "/xml-data/corpfiling/AttachHis/" in url:
            return 200, b"%PDF-1.4 fake"
        name = u.path.rsplit("/", 2)[-2] if u.path.endswith("/w") else u.path.rsplit("/", 1)[-1].replace(".aspx", "")
        self.calls.append((name, q))
        if name in self.refuse:
            return 403, b"Access Denied"
        return 200, json.dumps(self.answer(name, q)).encode()

    @staticmethod
    def answer(name, q):
        if name == "TabResults_PAR":
            body = F.FIX["NEWS" if q.get("tabtype") == "NEWS" else "RESULTS"]
            return body if isinstance(body, str) else json.dumps(body)  # BSE double-encodes this one
        if name == "Corp_detailedResult_Transpose_ng":
            return F.detail(q["Qtr"])
        if name == "StockReachGraphCas" and q.get("flag") == "12M":
            return F.HIST_12M
        if name == "AnnSubCategoryGetData":
            rows = F.ANN if q["strCat"] == "-1" else [r for r in F.ANN if r["CATEGORYNAME"] == "Result"]
            page = int(q["pageno"])
            return {"Table": rows[(page - 1) * 3: page * 3], "Table1": [{"ROWCNT": len(rows)}]}
        if name == "ListofScripData_new":
            return [r for r in F.LIST if q.get("segment") in ("Equity", "EQT0")
                    and (not q.get("scripName") or q["scripName"].lower() in r["Scrip_Name"].lower())]
        if name in F.FIX:
            return F.FIX[name]
        raise AssertionError(f"no fixture for {name}")

    def sent(self, name):
        return [q for n, q in self.calls if n == name]


@pytest.fixture
def fake(monkeypatch):
    f = FakeBse()
    monkeypatch.setattr(bse, "fetch", f)
    monkeypatch.setattr(tools, "_today", lambda: __import__("datetime").date(2026, 10, 19))
    monkeypatch.setattr(tools, "_now", lambda: __import__("datetime").datetime(2026, 10, 19, 12, 0, tzinfo=tools.IST))
    return f


@pytest.fixture(autouse=True)
def journal_in_tmp(tmp_path, monkeypatch):
    """No test writes to the real journal in ~/.bse-mcp."""
    monkeypatch.setenv("BSE_MCP_JOURNAL", str(tmp_path / "journal.db"))
