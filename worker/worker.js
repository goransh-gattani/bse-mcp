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
  const end = meta["Date End"] || "";
  return { quarter: labelFromEnd(end) || quarterLabel(id), bse_quarter_id: id.toFixed(2), period_begin: meta["Date Begin"], period_end: end, type: meta.Type, lines };
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
      let latest;
      if (upto) latest = quarterIdFor(upto);
      else {
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
      return { scripcode: sc, quarters: out, note: "Amounts as filed with BSE (Rs million unless the company reports otherwise); expenses negative. derived.* are computed here: ebitda = sales + materials + stock-in-trade purchases + inventory change + employee + other expenses." };
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
];

const SERVER_INFO = { name: "bse", version: "0.1.0" };
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
