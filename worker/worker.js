// bse-mcp Cloudflare Worker: a remote MCP server giving Claude live BSE India data by scrip code.
//
//   POST /mcp     MCP over Streamable HTTP (stateless JSON-RPC). Add https://<your-worker>/mcp as a
//                 custom connector in claude.ai, or `claude mcp add --transport http bse <url>`.
//   GET  /pdf     ?name=<attachment>&filename=<save as>: an announcement's PDF as a download.
//   GET  /        a short description.
//
// Variables (optional): MCP_TOKEN requires "Authorization: Bearer <token>" on /mcp;
// ALLOWED_ORIGIN restricts CORS (only matters for browser-based clients).
//
// BSE's CDN answers 403 to requests that don't look like a browser on bseindia.com, so every call
// carries Chrome's headers. BSE sometimes blocks Cloudflare's IP ranges; when it does, the tools
// report it and the Python server (pip install bse-mcp) from a home network is the fallback.
// Unofficial: not affiliated with BSE. Same tools as src/bse_mcp/tools.py.

const PDF_BASE = "https://www.bseindia.com/xml-data/corpfiling/AttachHis/";
const PDF_NAME = /^[A-Za-z0-9][A-Za-z0-9._-]*\.pdf$/i;
const UPSTREAM_HEADERS = {
  "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  "Accept-Language": "en-US,en;q=0.9",
  Origin: "https://www.bseindia.com",
  Referer: "https://www.bseindia.com/",
  "Sec-Ch-Ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
  "Sec-Ch-Ua-Mobile": "?0",
  "Sec-Ch-Ua-Platform": '"macOS"',
  "Sec-Fetch-Dest": "empty",
  "Sec-Fetch-Mode": "cors",
  "Sec-Fetch-Site": "same-site",
};

const corsHeaders = (env) => ({
  "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "*",
  Vary: "Origin",
});

export default {
  async fetch(request, env) {
    const cors = corsHeaders(env);
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
    const { pathname, searchParams } = new URL(request.url);
    const path = pathname.replace(/\/+$/, "");
    if (path === "/mcp") return mcp(request, env, cors);
    if (path === "/pdf") return downloadPdf(searchParams, cors);
    if (path === "") return new Response("bse-mcp: MCP server for live BSE India data. Add " + new URL(request.url).origin + "/mcp as a custom connector in claude.ai. https://github.com/goransh-gattani/bse-mcp\n", { headers: { ...cors, "Content-Type": "text/plain" } });
    return new Response("Not found", { status: 404, headers: cors });
  },
};

async function downloadPdf(params, cors) {
  const name = params.get("name") || "";
  if (!PDF_NAME.test(name)) return new Response("Bad attachment name", { status: 400, headers: cors });
  const filename = (params.get("filename") || name).replace(/[^A-Za-z0-9 ._()&-]/g, "_").trim() || "announcement.pdf";
  let upstream;
  try { upstream = await fetch(PDF_BASE + name, { headers: UPSTREAM_HEADERS }); } catch (err) { return new Response(`Could not reach BSE: ${err}`, { status: 502, headers: cors }); }
  if (!upstream.ok) return new Response(`BSE returned HTTP ${upstream.status}`, { status: upstream.status, headers: cors });
  return new Response(upstream.body, { headers: { ...cors, "Content-Type": "application/pdf", "Content-Disposition": `attachment; filename="${filename}"` } });
}

// ======================================================================== MCP server
const BASES = {
  api: "https://api.bseindia.com/BseIndiaAPI/api",
  realtime: "https://api.bseindia.com/RealTimeBseIndiaAPI/api",
  msource: "https://api.bseindia.com/MSource/1D",
};
// name -> [base, path, default params]; {scripcode}/{quarter} are filled by call_bse_api.
const ENDPOINTS = {
  getScripHeaderData: ["api", "getScripHeaderData/w", { Debtflag: "", scripcode: "{scripcode}", seriesid: "" }],
  ComHeadernew_par: ["api", "ComHeadernew_par/w", { quotetype: "", scripcode: "{scripcode}", seriesid: "" }],
  MarketDepth: ["realtime", "MarketDepth/w", { flag: "", quotetype: "EQ", scripcode: "{scripcode}" }],
  StockTrading: ["api", "StockTrading/w", { flag: "", quotetype: "EQ", scripcode: "{scripcode}" }],
  HighLow: ["api", "HighLow/w", { Type: "EQ", flag: "C", scripcode: "{scripcode}" }],
  PriceBand: ["api", "PriceBand/w", { scripcode: "{scripcode}", seriesid: "" }],
  SecurityPosition: ["api", "SecurityPosition/w", { scripcode: "{scripcode}" }],
  StockReachGraphCas: ["api", "StockReachGraphCas/w", { flag: "0", fromdate: "", scripcode: "{scripcode}", seriesid: "", todate: "" }],
  EQPeerGp: ["api", "EQPeerGp/w", { scripcomare: "", scripcode: "{scripcode}" }],
  TabResults_PAR_NEWS: ["api", "TabResults_PAR/w", { scripcode: "{scripcode}", tabtype: "NEWS" }],
  TabResults_PAR_RESULTS: ["api", "TabResults_PAR/w", { scripcode: "{scripcode}", tabtype: "RESULTS" }],
  ScripwiseCautionaryMsg: ["api", "ScripwiseCautionaryMsg/w", { scripcode: "{scripcode}" }],
  LeftMenunew: ["api", "LeftMenunew/w", { scripcode: "{scripcode}" }],
  Corp_detailedResult_Transpose_ng: ["api", "Corp_detailedResult_Transpose_ng/w", { Scrip_cd: "{scripcode}", Qtr: "{quarter}" }],
  Corp_BSEDnBResults_SEBI_Consolidated_Res_ng: ["api", "Corp_BSEDnBResults_SEBI_Consolidated_Res_ng/w", { Scrip_cd: "{scripcode}", QuarterID: "{quarter}" }],
  Corp_SEGMENTS_QUART_COMP_ng: ["api", "Corp_SEGMENTS_QUART_COMP_ng/w", { Scrip_cd: "{scripcode}", QuarterID: "{quarter}" }],
  Corp_Segments_Total_p_ng: ["api", "Corp_Segments_Total_p_ng/w", { Scrip_cd: "{scripcode}", QuarterID: "{quarter}" }],
  Corp_GET_BSEDnBResultNotes_ng: ["api", "Corp_GET_BSEDnBResultNotes_ng/w", { scrip_cd: "{scripcode}", currQtr: "{quarter}" }],
  AnnSubCategoryGetData: ["api", "AnnSubCategoryGetData/w", { strCat: "-1", strPrevDate: "", strScrip: "{scripcode}", strSearch: "P", strToDate: "", strType: "C", subcategory: "-1", pageno: "1" }],
  GetQuoteAllSearchDatabeta: ["msource", "GetQuoteAllSearchDatabeta.aspx", { searchString: "{scripcode}" }],
  ListofScripData_new: ["api", "ListofScripData_new/w", { Group: "", Scripcode: "", segment: "Equity", status: "Active", scripName: "" }],
  ddlGroup: ["api", "ddlGroup/w", { flag: "0" }],
  Mkt_GetTicker_ng: ["api", "Mkt_GetTicker_ng/w", { env: "1" }],
};
const SEGMENTS = ["Equity", "EQT0", "MF", "HS", "MB", "Preference Shares", "Debentures and Bonds", "Equity - Institutional Series",
  "Commercial Papers", "Government Securities", "Certificate of Deposit", "Treasury Bills"];

class ToolFail extends Error {} // message goes back to the model as an isError result

// BSE sometimes returns JSON inside a JSON string; decode those wherever they appear.
function unwrap(v) {
  if (typeof v === "string") {
    const t = v.trim();
    if ((t[0] === "{" && t.endsWith("}")) || (t[0] === "[" && t.endsWith("]"))) {
      try { return unwrap(JSON.parse(t)); } catch { return v; }
    }
    return v;
  }
  if (Array.isArray(v)) return v.map(unwrap);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, unwrap(x)]));
  return v;
}

async function bseGet(name, params) {
  const [base, path] = ENDPOINTS[name];
  const url = `${BASES[base]}/${path}?${new URLSearchParams(params)}`;
  let res;
  try { res = await fetch(url, { headers: UPSTREAM_HEADERS }); } catch (err) { throw new ToolFail(`Could not reach BSE for ${name}: ${err}`); }
  const text = await res.text();
  if (res.status === 403) throw new ToolFail(`BSE refused ${name} (HTTP 403) from this Worker's network; BSE sometimes blocks Cloudflare. Retry later, or run the local server instead (pip install bse-mcp).`);
  if (!res.ok) throw new ToolFail(`${name} failed: HTTP ${res.status}: ${text.slice(0, 200)}`);
  try { return unwrap(JSON.parse(text)); } catch { throw new ToolFail(`${name} did not return JSON: ${text.slice(0, 200)}`); }
}

const num = (v) => { const n = parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : null; };
const code = (sc) => {
  const c = String(sc ?? "").trim();
  if (!/^\d{5,6}$/.test(c)) throw new ToolFail(`scripcode must be the 5-6 digit BSE code (got ${JSON.stringify(sc)}); use search_scrips to find it`);
  return c;
};

// BSE numbers result quarters 126 = Jun-25, 127 = Sep-25, ... one per quarter (checked for ABB).
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fyLabel = (year, month) => {
  const q = { 5: 1, 8: 2, 11: 3, 2: 4 }[month];
  return q ? `Q${q} FY${String(month <= 2 ? year : year + 1).slice(-2)}` : null;
};
const quarterEnd = (id) => { const m = 2025 * 12 + 5 + 3 * (id - 126); return [Math.floor(m / 12), m % 12]; };
const quarterLabel = (id) => { const [y, m] = quarterEnd(id); return `${fyLabel(y, m)} (${MONTHS[m]}-${String(y).slice(-2)})`; };
const labelFromEnd = (end) => { const m = /^\d+-(\w{3})-(\d{2})$/.exec(end || ""); return m && MONTHS.includes(m[1]) ? fyLabel(2000 + +m[2], MONTHS.indexOf(m[1])) : null; };
const lastEndedQuarter = (d = new Date()) => 126 + Math.floor((d.getUTCFullYear() * 12 + d.getUTCMonth() - 1 - (2025 * 12 + 5)) / 3);
function quarterIdFor(label) {
  const s = String(label).trim().toUpperCase();
  if (/^\d{3}(\.\d+)?$/.test(s)) return Math.round(parseFloat(s));
  const m = /^Q([1-4])\s*FY\s*(\d{2}|\d{4})$/.exec(s);
  if (!m) throw new ToolFail(`quarter must look like 'Q1 FY27' (got ${JSON.stringify(label)})`);
  const q = +m[1], fy = +m[2] > 100 ? +m[2] : 2000 + +m[2];
  const month = { 1: 5, 2: 8, 3: 11, 4: 2 }[q], year = q < 4 ? fy - 1 : fy;
  return 126 + Math.floor((year * 12 + month - (2025 * 12 + 5)) / 3);
}

async function detailedResult(sc, id) {
  const d = await bseGet("Corp_detailedResult_Transpose_ng", { Scrip_cd: sc, Qtr: id.toFixed(2) });
  const rows = d && d.table1;
  if (!rows || !rows.length) return null;
  const meta = Object.fromEntries(rows.filter((r) => r.Header === "2").map((r) => [r.fld_desc, r.Value]));
  const lines = Object.fromEntries(rows.filter((r) => r.Header !== "2").map((r) => [r.fld_desc, num(r.Value)]));
  if (!Object.values(lines).some((v) => v != null)) return null; // BSE answers an unfiled quarter with empty meta rows only
  const begin = meta["Date Begin"] || "", end = meta["Date End"] || "";
  return { quarter: labelFromEnd(end) || quarterLabel(id), period: periodLabel(begin, end), bse_quarter_id: id.toFixed(2), period_begin: begin, period_end: end, type: meta.Type, lines };
}
// '01-Apr-26', '30-Jun-26' -> 'Apr–Jun 2026': the months the figures cover, whatever the company's FY.
function periodLabel(begin, end) {
  const rx = /^\d+-(\w{3})-(\d{2})$/;
  const b = rx.exec(begin || ""), e = rx.exec(end || "");
  if (!b || !e || !MONTHS.includes(b[1]) || !MONTHS.includes(e[1])) return null;
  const by = 2000 + +b[2], ey = 2000 + +e[2];
  return by === ey ? `${b[1]}–${e[1]} ${ey}` : `${b[1]} ${by}–${e[1]} ${ey}`;
}
const FINANCIALS_NOTE = "'quarter' names the quarter in the Indian April-March financial year; 'period' gives the months the figures cover, which is what to use for companies with another financial year (ABB India, for one, reports Jan-Dec). Amounts as filed with BSE (Rs million unless the company reports otherwise); expenses negative. derived.* are computed here: ebitda = sales + materials + stock-in-trade purchases + inventory change + employee + other expenses.";

async function financials(sc, n, upto) {
  let latest;
  if (upto) latest = quarterIdFor(upto);
  else {
    // The results tab links to the latest quarter; probe one ahead and a few behind in case that link lags.
    const tab = await bseGet("TabResults_PAR_RESULTS", { scripcode: sc, tabtype: "RESULTS" });
    const link = (tab && tab.resultinS && tab.resultinS[0] && tab.resultinS[0].LLQ) || "";
    const m = /qtr=([\d.]+)/.exec(link);
    const base = m ? Math.round(parseFloat(m[1])) : lastEndedQuarter();
    const probes = [base + 1, base, base - 1, base - 2, base - 3];
    const found = await Promise.all(probes.map((q) => detailedResult(sc, q)));
    const i = found.findIndex(Boolean);
    if (i < 0) throw new ToolFail(`BSE has no quarterly results for ${sc} around ${quarterLabel(base)}`);
    latest = probes[i];
  }
  // Ask for n quarters plus a few spares at once; stop after 4 unfiled in a row.
  const ids = Array.from({ length: n + 4 }, (_, i) => latest - i);
  const res = await Promise.all(ids.map((q) => detailedResult(sc, q)));
  const out = [];
  let misses = 0;
  for (const r of res) {
    if (out.length >= n || misses >= 4) break;
    if (!r) { misses++; continue; }
    misses = 0;
    out.push({ ...r, derived: derived(r.lines) });
  }
  return out;
}
const LINE = { sales: "Net Sales/Revenue From Operations", cmc: "Cost of Materials Consumed", purch: "Purchases of stock-in-trade",
  inv: "Changes in inventories of finished goods, work-in-progress and stock-in-trade", emp: "Employee benefit expense", oth: "Other Expenses",
  pbt: "Profit (+)/ Loss (-) from Ordinary Activities before Tax", tax: "Tax", pat: "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax" };
function derived(lines) {
  const g = (k) => lines[LINE[k]];
  const parts = ["sales", "cmc", "purch", "inv", "emp", "oth"].map(g);
  const ebitda = parts.every((p) => p != null) ? Math.round(parts.reduce((a, b) => a + b, 0) * 100) / 100 : null;
  const pct = (a, b) => (a != null && b ? Math.round((a / b) * 10000) / 10000 : null);
  const sales = g("sales"), pbt = g("pbt"), tax = g("tax"), pat = g("pat");
  return { ebitda, ebitda_margin: pct(ebitda, sales), pbt_margin: pct(pbt, sales), tax_rate: pct(tax != null ? -tax : null, pbt), pat_margin: pct(pat, sales) };
}
const plain = (t) => String(t || "").replace(/<\s*br\s*\/?>/gi, "\n").replace(/<[^>]+>/g, "")
  .replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, " ").replace(/\n{3,}/g, "\n\n").trim();
const ymd = (d) => d.toISOString().slice(0, 10).replace(/-/g, "");


// ======================================================================== analysis (mirrors src/bse_mcp/analysis.py)
const rnd = (x, nd = 4) => (x == null || !Number.isFinite(x) ? null : Math.round(x * 10 ** nd) / 10 ** nd);
const ratio = (a, b) => (a != null && b != null && b !== 0 ? a / b : null);
const growth = (now, before) => (now != null && before != null && before > 0 ? now / before - 1 : null);
const AL = { sales: "Net Sales/Revenue From Operations", other_income: "Other Income", cmc: "Cost of Materials Consumed",
  purch: "Purchases of stock-in-trade", inv: "Changes in inventories of finished goods, work-in-progress and stock-in-trade",
  emp: "Employee benefit expense", oth: "Other Expenses", dep: "Depreciation and amortisation expense", fin: "Finance Costs",
  pbt: "Profit (+)/ Loss (-) from Ordinary Activities before Tax", tax: "Tax",
  pat: "Net Profit (+)/ Loss (-) from Ordinary Activities after Tax", net: "Net Profit", eps: "Basic EPS for continuing operation" };
const FUNDAMENTAL_DEFINITIONS = {
  ebitda: "revenue + materials + stock-in-trade purchases + inventory change + employee cost + other expenses (operating profit before depreciation, interest, other income and tax)",
  ebit: "PBT + finance costs (includes other income)",
  interest_coverage: "EBIT / finance costs",
  pat: "profit after tax from continuing operations",
  net_profit: "reported net profit, including discontinued operations and other items",
  eps: "basic EPS from continuing operations (Rs per share)",
  tax_rate: "tax / PBT",
  other_income_share_of_pbt: "other income / PBT: how much of profit comes from outside operations",
  cost_structure: "each cost as a share of revenue; materials = materials consumed + stock-in-trade purchases + inventory change",
  yoy: "change against the quarter ending 12 months earlier; qoq: against the quarter ending 3 months earlier. None when that quarter is missing or the base is zero or negative",
  ttm: "sum of the latest 4 consecutive quarters (trailing twelve months); margins are TTM sums divided by TTM revenue",
  pe_ttm: "share price / TTM EPS (continuing operations)",
  price_to_sales_ttm: "market capitalisation / TTM revenue",
};
const GROWTH_KEYS = ["revenue", "ebitda", "pbt", "pat", "eps"];

function quarterMetrics(lines) {
  const g = (k) => (lines[AL[k]] ?? null);
  const sales = g("sales");
  const op = ["cmc", "purch", "inv", "emp", "oth"].map(g);
  const ebitda = sales != null && op.every((c) => c != null) ? sales + op.reduce((a, b) => a + b, 0) : null;
  const fin = g("fin") != null ? -g("fin") : null;
  const pbt = g("pbt"), tax = g("tax");
  const ebit = pbt != null && fin != null ? pbt + fin : null;
  const mat = ["cmc", "purch", "inv"].every((k) => g(k) != null) ? g("cmc") + g("purch") + g("inv") : null;
  const share = (v) => (v != null ? rnd(ratio(-v, sales)) : null);
  return {
    revenue: sales, other_income: g("other_income"), ebitda: rnd(ebitda, 2), ebit: rnd(ebit, 2), pbt, pat: g("pat"), net_profit: g("net"), eps: g("eps"),
    finance_costs: fin, depreciation: g("dep") != null ? -g("dep") : null,
    ebitda_margin: rnd(ratio(ebitda, sales)), pbt_margin: rnd(ratio(pbt, sales)), pat_margin: rnd(ratio(g("pat"), sales)),
    tax_rate: rnd(ratio(tax != null ? -tax : null, pbt)),
    interest_coverage: fin ? rnd(ratio(ebit, fin), 2) : null,
    other_income_share_of_pbt: rnd(ratio(g("other_income"), pbt)),
    cost_structure: { materials: share(mat), employee: share(g("emp")), other_expenses: share(g("oth")), depreciation: share(g("dep")) },
  };
}
const monthIndex = (end) => { const m = /^\d+-(\w{3})-(\d{2})$/.exec(end || ""); return m && MONTHS.includes(m[1]) ? (2000 + +m[2]) * 12 + MONTHS.indexOf(m[1]) : null; };
const pts = (a, b) => (a != null && b != null ? (a - b) * 100 : null);

function ttm(byM, latestM) {
  const win = [0, 1, 2, 3].map((i) => byM.get(latestM - 3 * i));
  if (win.some((w) => !w)) {
    const missing = [0, 1, 2, 3].filter((i) => !win[i]).map((i) => { const m = latestM - 3 * i; return `${MONTHS[m % 12]}-${String(Math.floor(m / 12)).slice(-2)}`; });
    return { available: false, reason: `needs 4 consecutive quarters; missing quarter(s) ending ${missing.join(", ")} (ask for more quarters)` };
  }
  const t = {};
  for (const k of ["revenue", "ebitda", "pbt", "pat", "net_profit", "eps", "other_income"]) {
    const v = win.map((w) => w.metrics[k]);
    t[k] = v.every((x) => x != null) ? rnd(v.reduce((a, b) => a + b, 0), 2) : null;
  }
  return { ...t, available: true, quarters: win.map((w) => w.period || w.quarter), ebitda_margin: rnd(ratio(t.ebitda, t.revenue)), pat_margin: rnd(ratio(t.pat, t.revenue)) };
}

function fundamentals(quarters) {
  const rows = quarters.map((q) => ({ quarter: q.quarter, period: q.period, period_end: q.period_end, _m: monthIndex(q.period_end), metrics: quarterMetrics(q.lines || {}) }))
    .filter((r) => r._m != null);
  const byM = new Map(rows.map((r) => [r._m, r]));
  for (const r of rows) {
    for (const [label, back] of [["yoy", 12], ["qoq", 3]]) {
      const prev = byM.get(r._m - back);
      r[label] = prev ? { ...Object.fromEntries(GROWTH_KEYS.map((k) => [k, rnd(growth(r.metrics[k], prev.metrics[k]))])),
        ebitda_margin_change_pts: rnd(pts(r.metrics.ebitda_margin, prev.metrics.ebitda_margin), 2) } : null;
    }
  }
  const out = { quarters: rows.map(({ _m, ...r }) => r) };
  out.ttm = rows.length ? ttm(byM, rows[0]._m) : { available: false, reason: "no quarters" };
  if (out.ttm.available) {
    const prior = ttm(byM, rows[0]._m - 12);
    out.ttm.growth_vs_prior_ttm = prior.available ? Object.fromEntries(GROWTH_KEYS.map((k) => [k, rnd(growth(out.ttm[k], prior[k]))])) : null;
  }
  return out;
}

function unitFactor(latestRevenue, card, latestEnd) {
  const known = [[0.1, "Rs million"], [0.01, "Rs lakh"], [1, "Rs crore"], [0.0001, "Rs thousand"]];
  let cardCr = null;
  if (card && typeof card === "object" && latestEnd) {
    const m = /^\d+-(\w{3})-(\d{2})$/.exec(latestEnd);
    const want = m ? `${m[1]}-${m[2]}` : null;
    const col = ["col2", "col3"].find((c) => card[c] === want);
    const row = (card.resultinCr || []).find((r) => String(r.title || "").toLowerCase().startsWith("revenue"));
    if (col && row) cardCr = num({ col2: row.v1, col3: row.v2 }[col]);
  }
  if (cardCr && latestRevenue) {
    const f = cardCr / latestRevenue;
    for (const [k, name] of known) if (Math.abs(f / k - 1) < 0.02) return { crore_per_unit: k, unit: name, basis: "matched against BSE's Rs-crore results card" };
    return { crore_per_unit: null, unit: null, basis: `filed figures don't match BSE's Rs-crore card by a known unit (ratio ${f.toPrecision(6)}); Rs-crore values skipped` };
  }
  return { crore_per_unit: 0.1, unit: "Rs million", basis: "assumed (BSE's label); couldn't cross-check against the Rs-crore card" };
}

function valuation(t, price, mcapCr, cpu) {
  if (!t.available) return { available: false, reason: "needs TTM figures: " + (t.reason || "") };
  const revCr = cpu && t.revenue != null ? t.revenue * cpu : null;
  const eps = t.eps;
  return { available: true, price, market_cap_cr: mcapCr, ttm_revenue_cr: rnd(revCr, 2), ttm_eps: eps,
    pe_ttm: eps && eps > 0 ? rnd(ratio(price, eps), 2) : null, price_to_sales_ttm: rnd(ratio(mcapCr, revCr), 2),
    not_computed: "EV/EBITDA, P/B, ROCE and debt ratios need the balance sheet, which BSE's results endpoints don't give" };
}

const TECHNICAL_DEFINITIONS = {
  returns: "close-to-close change over the last N trading days (1w=5, 1m=21, 3m=63, 6m=126, 1y=252, 3y=756, 5y=1260)",
  cagr: "compound annual growth from the first to the last close (calendar days when dates are given, else 252 trading days a year)",
  volatility_annualised: "sample standard deviation of daily log returns over the last 252 days (or all, if fewer) x sqrt(252)",
  max_drawdown: "largest peak-to-trough fall in the closes",
  sma: "simple moving average of the last N closes",
  ema: "exponential moving average, weight 2/(N+1), seeded with the SMA of the first N closes",
  macd: "EMA12 - EMA26; signal = EMA9 of MACD; histogram = MACD - signal",
  rsi_14: "Wilder's RSI: 100 - 100/(1 + average gain / average loss), Wilder-smoothed over 14 periods",
  bollinger_20_2: "SMA20 +/- 2 population standard deviations of the last 20 closes; percent_b = (close - lower)/(upper - lower)",
  range_52w: "high and low of the last 252 closes (closing prices only, so intraday extremes are not included)",
  trend: "SMA50 against SMA200: 'golden cross' state when above, 'death cross' state when below",
};
const WINDOWS = { "1w": 5, "1m": 21, "3m": 63, "6m": 126, "1y": 252, "3y": 756, "5y": 1260 };
const sma = (xs, n) => (xs.length >= n ? xs.slice(-n).reduce((a, b) => a + b, 0) / n : null);
function emaSeries(xs, n) {
  if (xs.length < n) return [];
  const a = 2 / (n + 1), out = [xs.slice(0, n).reduce((p, c) => p + c, 0) / n];
  for (const x of xs.slice(n)) out.push(a * x + (1 - a) * out[out.length - 1]);
  return out;
}
function rsi(xs, n = 14) {
  if (xs.length < n + 1) return null;
  const ch = xs.slice(1).map((b, i) => b - xs[i]);
  let gain = ch.slice(0, n).reduce((s, c) => s + Math.max(c, 0), 0) / n;
  let loss = ch.slice(0, n).reduce((s, c) => s + Math.max(-c, 0), 0) / n;
  for (const c of ch.slice(n)) { gain = (gain * (n - 1) + Math.max(c, 0)) / n; loss = (loss * (n - 1) + Math.max(-c, 0)) / n; }
  if (loss === 0) return gain > 0 ? 100 : 50;
  return 100 - 100 / (1 + gain / loss);
}
function maxDrawdown(xs, dates) {
  let peak = 0, worst = 0, at = [0, 0];
  xs.forEach((x, i) => { if (x > xs[peak]) peak = i; const dd = x / xs[peak] - 1; if (dd < worst) { worst = dd; at = [peak, i]; } });
  const d = (i) => (dates ? dates[i] : i);
  return worst < 0 ? { drawdown: rnd(worst), peak: d(at[0]), trough: d(at[1]) } : { drawdown: 0, peak: null, trough: null };
}
const stdev = (v, pop) => { const m = v.reduce((a, b) => a + b, 0) / v.length; return Math.sqrt(v.reduce((s, x) => s + (x - m) ** 2, 0) / (v.length - (pop ? 0 : 1))); };
function parseDate(s) {
  const t = String(s).trim();
  let m = /^(\d{4})-(\d{2})-(\d{2})/.exec(t) || /^(\d{4})(\d{2})(\d{2})$/.exec(t);
  if (m) return Date.UTC(+m[1], +m[2] - 1, +m[3]);
  m = /^(\d{1,2})[- ](\w{3})[- ](\d{4})$/.exec(t);
  if (m && MONTHS.includes(m[2].slice(0, 1).toUpperCase() + m[2].slice(1, 3).toLowerCase())) return Date.UTC(+m[3], MONTHS.indexOf(m[2].slice(0, 1).toUpperCase() + m[2].slice(1, 3).toLowerCase()), +m[1]);
  m = /^(\d{2})-(\d{2})-(\d{4})$/.exec(t);
  if (m) return Date.UTC(+m[3], +m[2] - 1, +m[1]);
  throw new ToolFail(`unrecognised date ${JSON.stringify(s)}; use YYYY-MM-DD`);
}

function technicals(closes, dates) {
  if (!Array.isArray(closes)) throw new ToolFail("closes must be a list of numbers");
  const xs = closes.map(Number);
  if (xs.length < 2) throw new ToolFail("need at least 2 closes");
  if (xs.some((x) => !Number.isFinite(x) || x <= 0)) throw new ToolFail("closes must be positive numbers");
  let parsed = null;
  if (dates != null) {
    if (dates.length !== xs.length) throw new ToolFail(`dates (${dates.length}) and closes (${xs.length}) differ in length`);
    parsed = dates.map(parseDate);
    if (parsed.some((d, i) => i && d <= parsed[i - 1])) throw new ToolFail("dates must be strictly increasing: pass the series oldest first");
  }
  const last = xs[xs.length - 1];
  const returns = Object.fromEntries(Object.entries(WINDOWS).filter(([, n]) => xs.length > n).map(([k, n]) => [k, rnd(last / xs[xs.length - 1 - n] - 1)]));
  const years = parsed ? (parsed[parsed.length - 1] - parsed[0]) / 864e5 / 365.25 : (xs.length - 1) / 252;
  const cagr = years >= 1 ? rnd((last / xs[0]) ** (1 / years) - 1) : null;
  const logr = xs.slice(1).map((b, i) => Math.log(b / xs[i])).slice(-252);
  const vol = logr.length >= 2 ? rnd(stdev(logr) * Math.sqrt(252)) : null;
  const e12 = emaSeries(xs, 12), e26 = emaSeries(xs, 26);
  let macd = null;
  if (e26.length) {
    const line = e26.map((v, i) => e12[e12.length - e26.length + i] - v);
    const sig = emaSeries(line, 9);
    if (sig.length) macd = { macd: rnd(line[line.length - 1]), signal: rnd(sig[sig.length - 1]), histogram: rnd(line[line.length - 1] - sig[sig.length - 1]) };
  }
  let boll = null;
  if (xs.length >= 20) {
    const w = xs.slice(-20), mid = w.reduce((a, b) => a + b, 0) / 20, sd = stdev(w, true), up = mid + 2 * sd, lo = mid - 2 * sd;
    boll = { middle: rnd(mid, 2), upper: rnd(up, 2), lower: rnd(lo, 2), percent_b: up > lo ? rnd((last - lo) / (up - lo)) : null, bandwidth: rnd((up - lo) / mid) };
  }
  const yr = xs.slice(-252), hi = Math.max(...yr), lo52 = Math.min(...yr);
  const s50 = sma(xs, 50), s200 = sma(xs, 200);
  const out = {
    count: xs.length, from: dates ? dates[0] : null, to: dates ? dates[dates.length - 1] : null, last_close: last,
    returns, cagr, volatility_annualised: vol, max_drawdown: maxDrawdown(xs, dates), max_drawdown_1y: maxDrawdown(xs.slice(-252), dates ? dates.slice(-252) : null),
    sma: Object.fromEntries([20, 50, 200].map((n) => [`sma_${n}`, rnd(sma(xs, n), 2)])),
    price_vs_sma: Object.fromEntries([20, 50, 200].map((n) => [`vs_sma_${n}`, sma(xs, n) ? rnd(last / sma(xs, n) - 1) : null])),
    ema: { ema_12: e12.length ? rnd(e12[e12.length - 1], 2) : null, ema_26: e26.length ? rnd(e26[e26.length - 1], 2) : null },
    macd, rsi_14: rnd(rsi(xs), 2), bollinger_20_2: boll,
    range_52w: { high: hi, low: lo52, position: hi > lo52 ? rnd((last - lo52) / (hi - lo52)) : null, below_high: rnd(last / hi - 1), window_days: yr.length },
    trend: s50 && s200 ? { sma50_vs_sma200: rnd(s50 / s200 - 1), state: s50 > s200 ? "golden cross (SMA50 above SMA200)" : "death cross (SMA50 below SMA200)" } : null,
  };
  const missing = [["sma_200 / trend", 200], ["1y range and volatility", 252], ["macd", 34], ["rsi_14", 15], ["bollinger", 20]].filter(([, need]) => xs.length < need).map(([n]) => n);
  if (missing.length) out.needs_more_data = `${xs.length} closes given; for ${missing.join(", ")} pass more history (~260 trading days covers everything except 3y/5y returns)`;
  return out;
}

const TOOLS = [
  {
    name: "search_scrips",
    description: "Find BSE scrip codes by company name, symbol, ISIN or code fragment (e.g. 'reliance', 'ABB', 'INE117A01022'). Returns up to 20 matches with scripcode, symbol, name, isin, market. Use the scripcode in the other tools.",
    inputSchema: { type: "object", properties: { query: { type: "string" } }, required: ["query"] },
    async run({ query }) {
      const rows = await bseGet("GetQuoteAllSearchDatabeta", { searchString: String(query || "").trim() });
      if (!Array.isArray(rows)) throw new ToolFail(`unexpected search reply: ${JSON.stringify(rows).slice(0, 200)}`);
      const seen = new Set();
      return rows.filter((r) => { const k = r.strSricpCode + "|" + r.Type; return !seen.has(k) && seen.add(k); }).slice(0, 20)
        .map((r) => ({ scripcode: r.strSricpCode, symbol: r.shortName, name: r.scripName, isin: r.Isin, market: (r.Type || "").trim() }));
    },
  },
  {
    name: "get_quote",
    description: "Live price and key facts for one BSE scrip: LTP, change, day/52-week range, volume, delivery %, market cap, EPS/PE/PB/ROE/margins (standalone and consolidated), group, sector/industry, ISIN, flags (ASM/GSM etc.).",
    inputSchema: { type: "object", properties: { scripcode: { type: "string", description: "5-6 digit BSE code" } }, required: ["scripcode"] },
    async run({ scripcode }) {
      const sc = code(scripcode);
      const [head, com, trade, hilo, pos, band] = await Promise.all([
        bseGet("getScripHeaderData", { Debtflag: "", scripcode: sc, seriesid: "" }), bseGet("ComHeadernew_par", { quotetype: "", scripcode: sc, seriesid: "" }),
        bseGet("StockTrading", { flag: "", quotetype: "EQ", scripcode: sc }), bseGet("HighLow", { Type: "EQ", flag: "C", scripcode: sc }),
        bseGet("SecurityPosition", { scripcode: sc }), bseGet("PriceBand", { scripcode: sc, seriesid: "" })]);
      const h = head.Header || {}, cur = head.CurrRate || {}, cmp = head.Cmpname || {};
      if (!cmp.FullN && !com.SecurityId) throw new ToolFail(`BSE has no equity scrip ${sc}; check the code with search_scrips`);
      const flags = Object.fromEntries(["ASMText", "GSMText", "EMSText", "SMSText", "IRPText", "DisplayText"].filter((k) => h[k]).map((k) => [k, h[k]]));
      const pick = (o, keys) => Object.fromEntries(keys.map((k) => [k, num(o[k])]));
      return {
        scripcode: sc, name: cmp.FullN, symbol: com.SecurityId, isin: com.ISIN, bse_url: cmp.SEOUrlEQ ? "https://www.bseindia.com" + cmp.SEOUrlEQ : null,
        price: { ltp: num(h.LTP || cur.LTP), change: num(cur.Chg), change_pct: num(cur.PcChg), open: num(h.Open), high: num(h.High), low: num(h.Low), prev_close: num(h.PrevClose), as_of: h.Ason },
        range: { week52_high: hilo.Fifty2WkHigh_unadj, week52_low: hilo.Fifty2WkLow_unadj, week_high_low: hilo.WeekHighLow, month_high_low: hilo.MonthHighLow, price_band: [band.LowerT, band.UpperT], circuit_limit: trade.CktLimit },
        trading: { wap: num(trade.WAP), turnover: trade.Turnover ? `${trade.Turnover} ${trade.Turnoverin || ""}`.trim() : null, traded_qty: num(trade.TTQ),
          two_week_avg_qty: trade.TwoWkAvgQty ? `${trade.TwoWkAvgQty} ${trade.TwoWkAvgQtyin || ""}`.trim() : null, delivered_qty: num(pos.DeliverableQty), delivery_pct: num(pos.PcDQ_TQ),
          delivery_as_of: pos.TradeDate, market_cap_cr: num(trade.MktCapFull), free_float_mcap_cr: num(trade.MktCapFF), ex_date: trade.ExDate },
        ratios: { standalone: pick(com, ["EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM"]),
          consolidated: Object.fromEntries(["EPS", "CEPS", "PE", "PB", "ROE", "OPM", "NPM"].map((k) => [k, num(com["Con" + k])])) },
        classification: Object.fromEntries(["Group", "Index", "Sector", "IndustryNew", "Industry", "IGroup", "ISubGroup", "FaceVal", "SetlType"].map((k) => [k, com[k]])),
        flags,
      };
    },
  },
  {
    name: "get_market_depth",
    description: "Top-5 bids and asks (price and quantity) with totals for one BSE scrip.",
    inputSchema: { type: "object", properties: { scripcode: { type: "string" } }, required: ["scripcode"] },
    async run({ scripcode }) {
      const sc = code(scripcode);
      const d = await bseGet("MarketDepth", { flag: "", quotetype: "EQ", scripcode: sc });
      const five = [1, 2, 3, 4, 5];
      return { scripcode: sc, as_of: d.dttm, bids: five.map((i) => ({ price: num(d["BPrice" + i]), qty: num(d["BQty" + i]) })),
        asks: five.map((i) => ({ price: num(d["SPrice" + i]), qty: num(d["SQty" + i]) })), total_bid_qty: num(d.TotalBQty), total_ask_qty: num(d.TotalSQty) };
    },
  },
  {
    name: "get_peers",
    description: "BSE's peer group for a scrip: each peer's code, LTP, change %, PE, PB, EPS, revenue and PAT (Rs Cr), OPM, NPM, 52-week range and the quarter those results are from.",
    inputSchema: { type: "object", properties: { scripcode: { type: "string" } }, required: ["scripcode"] },
    async run({ scripcode }) {
      const sc = code(scripcode);
      const d = await bseGet("EQPeerGp", { scripcomare: "", scripcode: sc });
      if (!d || !Array.isArray(d.Table) || !d.Table.length) throw new ToolFail(`BSE returned no peer table for ${sc}`);
      const keys = ["Name", "scrip_cd", "LTP", "Change", "PE", "PB", "EPS", "Revenue", "PAT", "OPM", "NPM", "w52hi", "w52lo", "Results_QuarterName"];
      return d.Table.map((r) => Object.fromEntries(keys.map((k) => [k, r[k]])));
    },
  },
  {
    name: "get_financials",
    description: "Quarterly P&L from BSE's results filings, newest first, with derived EBITDA, margins and tax rate. quarters: how many (1-16). upto: newest quarter to include like 'Q1 FY27'; by default the latest BSE has results for is detected. Values as originally filed, expenses negative, Rs million for most companies.",
    inputSchema: { type: "object", properties: { scripcode: { type: "string" }, quarters: { type: "integer", default: 5 }, upto: { type: "string", description: "e.g. Q4 FY26" } }, required: ["scripcode"] },
    async run({ scripcode, quarters = 5, upto }) {
      const sc = code(scripcode);
      const n = Math.max(1, Math.min(16, parseInt(quarters, 10) || 5));
      return { scripcode: sc, quarters: await financials(sc, n, upto), note: FINANCIALS_NOTE };
    },
  },
  {
    name: "get_announcements",
    description: "Corporate announcements and filings for a scrip from BSE's announcements feed, newest first, with PDF links. months: look back 1-12 (BSE returns nothing for longer). category: 'all' or 'results'. page: 1-based, about 50 rows per page; 'total' says how many exist.",
    inputSchema: { type: "object", properties: { scripcode: { type: "string" }, months: { type: "integer", default: 12 }, category: { type: "string", enum: ["all", "results"], default: "all" }, page: { type: "integer", default: 1 } }, required: ["scripcode"] },
    async run({ scripcode, months = 12, category = "all", page = 1 }, origin) {
      const sc = code(scripcode);
      if (!["all", "results"].includes(category)) throw new ToolFail("category must be 'all' or 'results'");
      const mo = Math.max(1, Math.min(12, parseInt(months, 10) || 12));
      const now = new Date(), since = new Date(now);
      since.setUTCDate(Math.min(now.getUTCDate(), 28));
      since.setUTCMonth(since.getUTCMonth() - mo);
      const [cat, sub] = category === "results" ? ["Result", "Financial Results"] : ["-1", "-1"];
      const d = await bseGet("AnnSubCategoryGetData", { strCat: cat, strPrevDate: ymd(since), strScrip: sc, strSearch: "P", strToDate: ymd(now), strType: "C", subcategory: sub, pageno: String(Math.max(1, parseInt(page, 10) || 1)) });
      const rows = (d && d.Table) || [];
      const total = num(d && d.Table1 && d.Table1[0] && d.Table1[0].ROWCNT);
      return { scripcode: sc, from: since.toISOString().slice(0, 10), to: now.toISOString().slice(0, 10), page, total: total ?? rows.length,
        announcements: rows.map((r) => { const att = (r.ATTACHMENTNAME || "").trim(); return { date: r.NEWS_DT || r.DT_TM, headline: plain(r.HEADLINE || r.NEWSSUB), category: r.CATEGORYNAME, subcategory: r.SUBCATNAME,
          attachment: att || null, pdf_url: att ? PDF_BASE + encodeURIComponent(att) : null, pdf_download_url: att ? `${origin}/pdf?name=${encodeURIComponent(att)}` : null }; }) };
    },
  },
  {
    name: "list_scrips",
    description: "List BSE securities from the List of Securities page: segment (Equity, EQT0, MF, HS, MB, 'Preference Shares', 'Debentures and Bonds', 'Equity - Institutional Series', 'Commercial Papers', 'Government Securities', 'Certificate of Deposit', 'Treasury Bills'), status (Active/Suspended/Delisted/''), group code, name fragment, or one exact code. Returns up to `limit` rows (default 200) and the total. Add a filter for big segments.",
    inputSchema: { type: "object", properties: { segment: { type: "string", default: "Equity" }, status: { type: "string", default: "Active" }, group: { type: "string", default: "" }, name_contains: { type: "string", default: "" }, scripcode: { type: "string", default: "" }, limit: { type: "integer", default: 200 } } },
    async run({ segment = "Equity", status = "Active", group = "", name_contains = "", scripcode = "", limit = 200 }) {
      if (!SEGMENTS.includes(segment)) throw new ToolFail(`segment must be one of ${SEGMENTS.join(", ")}`);
      const rows = await bseGet("ListofScripData_new", { Group: group, Scripcode: String(scripcode).trim(), segment, status, scripName: String(name_contains).trim() });
      if (!Array.isArray(rows)) throw new ToolFail(`unexpected list reply: ${JSON.stringify(rows).slice(0, 200)}`);
      const n = Math.max(1, parseInt(limit, 10) || 200);
      const keys = ["SCRIP_CD", "scrip_id", "Scrip_Name", "Issuer_Name", "Segment", "Status", "GROUP", "FACE_VALUE", "ISIN_NUMBER", "Mktcap"];
      return { total: rows.length, returned: Math.min(rows.length, n), rows: rows.slice(0, n).map((r) => Object.fromEntries(keys.map((k) => [k, r[k]]))) };
    },
  },
  {
    name: "call_bse_api",
    description: `Call any documented BSE endpoint and return its raw decoded JSON. endpoint is one of: ${Object.keys(ENDPOINTS).join(", ")}. Default params are filled from scripcode and quarter (a BSE quarter id like '130.00' or 'Q1 FY27'); anything in params overrides them.`,
    inputSchema: { type: "object", properties: { endpoint: { type: "string" }, params: { type: "object", additionalProperties: { type: "string" } }, scripcode: { type: "string", default: "" }, quarter: { type: "string", default: "" } }, required: ["endpoint"] },
    async run({ endpoint, params = {}, scripcode = "", quarter = "" }) {
      if (!ENDPOINTS[endpoint]) throw new ToolFail(`unknown endpoint ${JSON.stringify(endpoint)}; see the tool description for the list`);
      const qid = quarter ? quarterIdFor(quarter).toFixed(2) : "";
      const filled = Object.fromEntries(Object.entries(ENDPOINTS[endpoint][2]).map(([k, v]) => [k, v.replace("{scripcode}", String(scripcode).trim()).replace("{quarter}", qid)]));
      for (const [k, v] of Object.entries(params || {})) filled[k] = String(v);
      return bseGet(endpoint, filled);
    },
  },
  {
    name: "analyze_fundamentals",
    description: "Computed fundamentals for a BSE scrip from its quarterly filings: revenue, EBITDA, PBT, PAT, EPS with YoY and QoQ growth (matched by period, not by position), margins and margin change, cost structure as % of revenue, interest coverage, tax rate, other income as % of PBT, TTM totals and TTM growth, and TTM P/E and price/sales from the live price. quarters: how many to fetch (8 gives TTM and its growth). Use this instead of doing the arithmetic yourself.",
    inputSchema: { type: "object", properties: { scripcode: { type: "string" }, quarters: { type: "integer", default: 8 } }, required: ["scripcode"] },
    async run({ scripcode, quarters = 8 }) {
      const sc = code(scripcode);
      const n = Math.max(1, Math.min(16, parseInt(quarters, 10) || 8));
      const qs = await financials(sc, n);
      if (!qs.length) throw new ToolFail(`BSE returned no quarterly results for ${sc}`);
      const out = fundamentals(qs);
      const [head, trade, card, com] = await Promise.all([
        bseGet("getScripHeaderData", { Debtflag: "", scripcode: sc, seriesid: "" }), bseGet("StockTrading", { flag: "", quotetype: "EQ", scripcode: sc }),
        bseGet("TabResults_PAR_RESULTS", { scripcode: sc, tabtype: "RESULTS" }), bseGet("ComHeadernew_par", { quotetype: "", scripcode: sc, seriesid: "" })]);
      const h = head.Header || {}, cur = head.CurrRate || {};
      const latest = out.quarters[0];
      const unit = unitFactor(latest ? latest.metrics.revenue : null, card, latest ? latest.period_end : null);
      out.valuation = valuation(out.ttm, num(h.LTP || cur.LTP), num(trade.MktCapFull), unit.crore_per_unit);
      out.valuation.bse_reported = { pe: num(com.PE), eps: num(com.EPS), note: "BSE's own P/E and EPS; their EPS basis (e.g. annual, including discontinued items) can differ from TTM continuing EPS" };
      return { scripcode: sc, unit, ...out, definitions: FUNDAMENTAL_DEFINITIONS,
        note: "Figures are standalone as filed with BSE; amounts in the filed unit (see 'unit') unless the key ends in _cr. Further reading on these ratios: Zerodha Varsity, Fundamental Analysis https://zerodha.com/varsity/module/fundamental-analysis/" };
    },
  },
  {
    name: "analyze_prices",
    description: "Technical indicators on a daily closing-price series, oldest first (e.g. from an NSE price-history tool): returns over 1w-5y, CAGR, annualised volatility, max drawdown, SMA 20/50/200, EMA 12/26, MACD(12,26,9), RSI(14), Bollinger(20,2), 52-week range position and the SMA50/200 trend. closes: numbers; dates: optional matching dates (YYYY-MM-DD). ~260 closes covers all but 3y/5y returns.",
    inputSchema: { type: "object", properties: { closes: { type: "array", items: { type: "number" } }, dates: { type: "array", items: { type: "string" } } }, required: ["closes"] },
    async run({ closes, dates }) {
      return { ...technicals(closes, dates ?? null), definitions: TECHNICAL_DEFINITIONS,
        note: "Computed on the closes given (oldest first). Indicators describe past prices; they are not forecasts or advice. Further reading: Zerodha Varsity, Technical Analysis https://zerodha.com/varsity/module/technical-analysis/" };
    },
  },
];

const SERVER_INFO = { name: "bse", version: "0.2.0" };
const INSTRUCTIONS = "Live data from BSE India (Bombay Stock Exchange) by scrip code. Start with search_scrips when you only have a company name; the 5-6 digit code it returns is what every other tool takes. Amounts from get_financials are as BSE labels them (Rs million for most companies, as originally filed). Unofficial: not affiliated with BSE.";
const PROTOCOLS = ["2025-06-18", "2025-03-26", "2024-11-05"];

async function mcp(request, env, cors) {
  const headers = { ...cors, "Content-Type": "application/json" };
  if (env.MCP_TOKEN && request.headers.get("Authorization") !== `Bearer ${env.MCP_TOKEN}`) {
    return new Response(JSON.stringify({ error: "unauthorized" }), { status: 401, headers: { ...headers, "WWW-Authenticate": "Bearer" } });
  }
  if (request.method === "GET") return new Response("This MCP server is stateless: POST JSON-RPC here.", { status: 405, headers: { ...cors, Allow: "POST" } });
  if (request.method === "DELETE") return new Response(null, { status: 200, headers: cors });
  if (request.method !== "POST") return new Response("Method not allowed", { status: 405, headers: cors });
  let msg;
  try { msg = await request.json(); } catch { return rpcError(null, -32700, "Parse error", headers); }
  const batch = Array.isArray(msg) ? msg : [msg];
  const origin = new URL(request.url).origin;
  const replies = (await Promise.all(batch.map((m) => handle(m, origin)))).filter(Boolean);
  if (!replies.length) return new Response(null, { status: 202, headers: cors }); // notifications only
  return new Response(JSON.stringify(Array.isArray(msg) ? replies : replies[0]), { headers });
}
const rpcError = (id, code, message, headers) => new Response(JSON.stringify({ jsonrpc: "2.0", id, error: { code, message } }), { headers });

async function handle(m, origin) {
  if (!m || m.jsonrpc !== "2.0" || typeof m.method !== "string") return { jsonrpc: "2.0", id: (m && m.id) ?? null, error: { code: -32600, message: "Invalid Request" } };
  const { id, method, params = {} } = m;
  if (id === undefined) return null; // a notification (e.g. notifications/initialized): nothing to send back
  const ok = (result) => ({ jsonrpc: "2.0", id, result });
  switch (method) {
    case "initialize": {
      const asked = params.protocolVersion;
      return ok({ protocolVersion: PROTOCOLS.includes(asked) ? asked : PROTOCOLS[0], capabilities: { tools: {} }, serverInfo: SERVER_INFO, instructions: INSTRUCTIONS });
    }
    case "ping": return ok({});
    case "tools/list": return ok({ tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })) });
    case "tools/call": {
      const tool = TOOLS.find((t) => t.name === params.name);
      if (!tool) return { jsonrpc: "2.0", id, error: { code: -32602, message: `Unknown tool: ${params.name}` } };
      try {
        const result = await tool.run(params.arguments || {}, origin);
        return ok({ content: [{ type: "text", text: JSON.stringify(result, null, 2) }], isError: false });
      } catch (err) {
        if (err instanceof ToolFail) return ok({ content: [{ type: "text", text: err.message }], isError: true });
        return ok({ content: [{ type: "text", text: `Error executing tool ${tool.name}: ${err && err.message}` }], isError: true });
      }
    }
    case "resources/list": return ok({ resources: [] });
    case "prompts/list": return ok({ prompts: [] });
    default: return { jsonrpc: "2.0", id, error: { code: -32601, message: `Method not found: ${method}` } };
  }
}

// Exported for tests (worker/test/worker.test.mjs); Cloudflare only uses the default export.
export { rsi, maxDrawdown, emaSeries, technicals, fundamentals };
