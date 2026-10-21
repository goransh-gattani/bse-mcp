// Run with:  node --test worker/test/worker.test.mjs   (from the repo root). BSE answers come from fixtures.json.
import w, { rsi, maxDrawdown, atr, adx, stochastic, swings, fibonacci, rsiDivergence, toWeekly, tradeCosts } from "../worker.js";
import fs from "node:fs";
const F = JSON.parse(fs.readFileSync(new URL("./fixtures.json", import.meta.url), "utf8"));
const calls = []; let fail = new Set();
globalThis.fetch = async (u) => {
  const url = new URL(String(u)); const q = Object.fromEntries(url.searchParams);
  const name = url.pathname.endsWith("/w") ? url.pathname.split("/").at(-2) : url.pathname.split("/").at(-1).replace(".aspx", "");
  calls.push([name, q]);
  const J = (b, status = 200) => new Response(typeof b === "string" ? b : JSON.stringify(b), { status, headers: { "Content-Type": "application/json" } });
  if (fail.has(name)) return new Response("Access Denied", { status: 403 });
  if (name === "TabResults_PAR") { const b = F.FIX[q.tabtype === "NEWS" ? "NEWS" : "RESULTS"]; return J(JSON.stringify(typeof b === "string" ? b : JSON.stringify(b))); }
  if (name === "Corp_detailedResult_Transpose_ng") return J(F.detail[q.Qtr] || { table1: [] });
  if (name === "StockReachGraphCas" && q.flag === "12M") return J(F.HIST_12M);
  if (name === "AnnSubCategoryGetData") { const rows = q.strCat === "-1" ? F.ANN : F.ANN.filter((r) => r.CATEGORYNAME === "Result"); const p = +q.pageno; return J({ Table: rows.slice((p - 1) * 3, p * 3), Table1: [{ ROWCNT: rows.length }] }); }
  if (name === "ListofScripData_new") return J(F.LIST.filter((r) => ["Equity", "EQT0"].includes(q.segment) && (!q.scripName || r.Scrip_Name.toLowerCase().includes(q.scripName.toLowerCase()))));
  if (F.FIX[name] !== undefined) return J(F.FIX[name]);
  throw new Error("unmocked " + u);
};
const fails = [];
const check = (c, l) => { console.log((c ? "PASS " : "FAIL ") + l); if (!c) fails.push(l); };
const W = "https://bse-proxy.x.workers.dev";
const env = {};
const rpc = async (body, extra = {}) => w.fetch(new Request(W + "/mcp", { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", ...extra.headers }, body: JSON.stringify(body) }), extra.env || env);
const call = async (name, args) => { const r = await rpc({ jsonrpc: "2.0", id: 7, method: "tools/call", params: { name, arguments: args } }); const j = await r.json(); return j.result; };
const text = (res) => JSON.parse(res.content[0].text);

let r = await rpc({ jsonrpc: "2.0", id: 1, method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: { name: "t", version: "0" } } });
let j = await r.json();
check(r.status === 200 && j.result.protocolVersion === "2025-03-26" && j.result.serverInfo.name === "bse" && j.result.capabilities.tools, "initialize echoes supported protocol");
r = await rpc({ jsonrpc: "2.0", method: "notifications/initialized" });
check(r.status === 202, "notification -> 202");
r = await rpc({ jsonrpc: "2.0", id: 2, method: "tools/list" }); j = await r.json();
check(j.result.tools.length === 12 && j.result.tools.every((t) => t.name && t.description && t.inputSchema.type === "object"), `tools/list (${j.result.tools.map((t) => t.name).join(",")})`);
r = await rpc({ jsonrpc: "2.0", id: 3, method: "nope" }); j = await r.json(); check(j.error && j.error.code === -32601, "unknown method -> -32601");
r = await w.fetch(new Request(W + "/mcp", { method: "POST", body: "{bad" }), env); check((await r.json()).error.code === -32700, "parse error");
r = await w.fetch(new Request(W + "/mcp"), env); check(r.status === 405, "GET /mcp -> 405");

let s = text(await call("search_scrips", { query: "abb" }));
check(s.length === 3 && s[0].scripcode === "500002", "search_scrips");
let q = text(await call("get_quote", { scripcode: "500002" }));
check(q.name === "ABB India Ltd" && q.price.ltp === 6963 && q.price.change_pct === 2.76 && q.trading.delivery_pct === 64.27 && q.ratios.standalone.PE === 49.38 && q.classification.Group === "A" && q.isin === "INE117A01022", "get_quote");
let e = await call("get_quote", { scripcode: "abc" });
check(e.isError && e.content[0].text.includes("search_scrips"), "argument error is isError with message");
let d = text(await call("get_market_depth", { scripcode: "500002" }));
check(d.bids[0].price === 6962.5 && d.total_bid_qty === 9390, "market depth");
let p = text(await call("get_peers", { scripcode: "500002" }));
check(p.length === 4 && p.some((x) => /Hitachi/.test(x.Name)), "peers");
calls.length = 0;
let f = text(await call("get_financials", { scripcode: "500002", quarters: 5 }));
check(f.quarters.map((x) => x.quarter).join(",") === "Q1 FY27,Q4 FY26,Q3 FY26,Q2 FY26,Q1 FY26", `financials auto latest + skip unfiled (${f.quarters.map((x) => x.quarter)})`);
check(f.quarters[0].period === "Apr–Jun 2026" && f.quarters.every((x) => Object.keys(x.lines).length), "period label; BSE's empty placeholder for 131 is not a quarter");
check(f.quarters[0].derived.ebitda === 4470.4 && f.quarters[0].derived.ebitda_margin === 0.1256 && f.quarters[0].derived.tax_rate === 0.258, `derived (${JSON.stringify(f.quarters[0].derived)})`);
check(calls.some(([n, qq]) => n === "Corp_detailedResult_Transpose_ng" && qq.Qtr === "131.00"), "probed one quarter ahead of the results link");
f = text(await call("get_financials", { scripcode: "500002", quarters: 1, upto: "Q4 FY26" }));
check(f.quarters.length === 1 && f.quarters[0].quarter === "Q4 FY26", "financials upto by name");
let a = text(await call("get_announcements", { scripcode: "500002", months: 6 }));
check(a.total === 7 && a.announcements.length === 3 && a.announcements[0].pdf_url.endsWith("/AttachHis/w1.pdf") && a.announcements[0].pdf_download_url === W + "/pdf?name=w1.pdf" && a.announcements[2].pdf_url === null, "announcements with pdf urls");
check(!a.announcements[0].headline.includes("<") && a.announcements[0].headline.includes("Closure"), "headline html stripped");
let sent = calls.filter(([n]) => n === "AnnSubCategoryGetData").at(-1)[1];
check(sent.strPrevDate < sent.strToDate && sent.strPrevDate.slice(0, 6) === "202604", `6 months back (${sent.strPrevDate}..${sent.strToDate})`);
a = text(await call("get_announcements", { scripcode: "500002", category: "results" }));
check(a.total === 2, "results filter");
let l = text(await call("list_scrips", { name_contains: "abb", limit: 1 }));
check(l.total === 2 && l.returned === 1, "list_scrips");
e = await call("list_scrips", { segment: "Bogus" }); check(e.isError && /segment must be/.test(e.content[0].text), "bad segment");
let raw = text(await call("call_bse_api", { endpoint: "Corp_detailedResult_Transpose_ng", scripcode: "500002", quarter: "Q1 FY27" }));
check(raw.table1.length > 20 && calls.at(-1)[1].Qtr === "130.00", "call_bse_api fills quarter by name");
raw = text(await call("call_bse_api", { endpoint: "SecurityPosition", scripcode: "500002" }));
check(raw.DeliverableQty !== undefined, "call_bse_api unwraps double json");
fail.add("getScripHeaderData");
e = await call("get_quote", { scripcode: "500002" });
check(e.isError && /403/.test(e.content[0].text) && /pip install bse-mcp/.test(e.content[0].text), "403 -> isError with remedy");
fail.clear();

// ---- analysis tools: same expectations as tests/test_analysis.py
let fa = text(await call("analyze_fundamentals", { scripcode: "500002", quarters: 8 }));
let la = fa.quarters[0];
check(fa.unit.unit === "Rs million" && la.metrics.ebitda === 4470.4 && la.metrics.interest_coverage === 292.68 && la.metrics.other_income_share_of_pbt === 0.1858, `fundamentals metrics (${JSON.stringify(la.metrics).slice(0, 120)})`);
check(JSON.stringify(la.metrics.cost_structure) === JSON.stringify({ materials: 0.5961, employee: 0.0705, other_expenses: 0.2078, depreciation: 0.011 }), "cost structure");
check(JSON.stringify(la.yoy) === JSON.stringify({ revenue: 0.1207, ebitda: 0.0796, pbt: 0.052, pat: 0.0511, eps: 0.0505, ebitda_margin_change_pts: -0.48 }), `yoy (${JSON.stringify(la.yoy)})`);
check(la.qoq.revenue === 0.1177 && fa.quarters.at(-1).yoy === null, "qoq; no yoy for the oldest");
check(fa.ttm.available && fa.ttm.revenue === 136106.6 && fa.ttm.eps === 73.4 && fa.ttm.growth_vs_prior_ttm === null, `ttm (${JSON.stringify(fa.ttm).slice(0, 120)})`);
check(fa.valuation.ttm_revenue_cr === 13610.66 && fa.valuation.pe_ttm === Math.round(6963 / 73.4 * 100) / 100 && fa.valuation.price_to_sales_ttm === Math.round(147551.8 / 13610.66 * 100) / 100 && fa.valuation.bse_reported.pe === 49.38, `valuation (${JSON.stringify(fa.valuation).slice(0, 160)})`);
fa = text(await call("analyze_fundamentals", { scripcode: "500002", quarters: 2 }));
check(fa.ttm.available === false && /4 consecutive/.test(fa.ttm.reason) && fa.valuation.available === false, "ttm needs 4 consecutive quarters");
const RSI_CLOSES = [44.3389, 44.0902, 44.1497, 43.6124, 44.2779, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826, 45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439];
const rsis = [15, 16, 17, 18, 19, 20].map((k) => Math.round(rsi(RSI_CLOSES.slice(0, k)) * 100) / 100);
check(JSON.stringify(rsis) === JSON.stringify([70.53, 66.32, 66.55, 69.41, 66.36, 57.97]), `RSI matches StockCharts example (${rsis})`);
const line = Array.from({ length: 250 }, (_, i) => i + 1);
let ta = text(await call("analyze_prices", { closes: line }));
check(Math.abs(ta.macd.macd - 7) < 1e-9 && Math.abs(ta.macd.signal - 7) < 1e-9 && ta.ema.ema_12 === 244.5 && ta.ema.ema_26 === 237.5 && ta.ema.ema_50 === 225.5 && ta.rsi_14 === 100 && /golden/.test(ta.trend.state), `macd/ema exact on a line (${JSON.stringify(ta.macd)})`);
// ---- BSE's 12-month price chart as a daily series, and analyze_prices fetching it by scripcode
calls.length = 0;
let ph = text(await call("get_price_history", { scripcode: "500002" }));
check(calls[0][1].flag === "12M" && ph.bars === 250 && ph.from === "2025-10-21" && ph.dates[1] === "2025-10-22" && ph.closes[0] === 5000 && ph.volumes[0] === 2000 && ph.to === ph.dates.at(-1), `get_price_history (${ph.from}..${ph.to})`);
ta = text(await call("analyze_prices", { scripcode: "500002" }));
check(ta.count === 250 && ta.from === "2025-10-21" && /BSE's daily closes/.test(ta.source) && ta.sma.sma_200 != null && Boolean(ta.ohlc_indicators) && !ta.price_jumps && ta.volume.avg_20 > 0 && ta.swings.lows.length === 5 && [...ta.swings.lows, ...ta.swings.highs].every((p) => p.rsi > 0 && p.rsi < 100), "analyze_prices by scripcode");
let tw = text(await call("analyze_prices", { scripcode: "500002", timeframe: "weekly" }));
check(tw.timeframe === "weekly" && tw.count >= 50 && tw.count <= 53, `weekly from BSE closes (${tw.count} bars)`);
e = await call("analyze_prices", { scripcode: "500002", closes: [1, 2] }); check(e.isError && /not both/.test(e.content[0].text), "scripcode and a series together are rejected");
e = await call("analyze_prices", {}); check(e.isError && /scripcode/.test(e.content[0].text), "no input says what to pass");
const jd = Array.from({ length: 40 }, (_, i) => new Date(Date.UTC(2026, 0, 1 + i)).toISOString().slice(0, 10));
let tj = text(await call("analyze_prices", { closes: [...Array(20).fill(100), ...Array(20).fill(50)], dates: jd }));
check(JSON.stringify(tj.price_jumps.bars) === JSON.stringify([{ at: jd[20], change: -0.5 }]) && !text(await call("analyze_prices", { closes: line.slice(100) })).price_jumps, `price_jumps (${JSON.stringify(tj.price_jumps && tj.price_jumps.bars)})`);
ta = text(await call("analyze_prices", { closes: Array.from({ length: 20 }, (_, i) => i + 1) }));
check(ta.bollinger_20_2.middle === 10.5 && Math.abs(ta.bollinger_20_2.upper - (10.5 + 2 * Math.sqrt(399 / 12))) < 0.01 && Boolean(ta.needs_more_data), "bollinger population sd");
check(JSON.stringify(maxDrawdown([100, 120, 90, 130], ["d0", "d1", "d2", "d3"])) === JSON.stringify({ drawdown: -0.25, peak: "d1", trough: "d2" }), "max drawdown");
ta = text(await call("analyze_prices", { closes: [100, 121], dates: ["2024-01-01", "2026-01-01"] }));
check(Math.abs(ta.cagr - 0.0998) < 1e-3, `cagr with dates (${ta.cagr})`);
e = await call("analyze_prices", { closes: [1, 2, 3], dates: ["2026-01-03", "2026-01-02", "2026-01-01"] });
check(e.isError && /oldest first/.test(e.content[0].text), "rejects descending dates");
e = await call("analyze_prices", { closes: [1, -2, 3] });
check(e.isError && /positive/.test(e.content[0].text), "rejects non-positive closes");

// ---- OHLC indicators and sizing: same hand-worked values as tests/test_analysis.py and tests/test_sizing.py
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const rc = Array.from({ length: 60 }, (_, i) => 100 + i), rh = rc.map((x) => x + 1), rl = rc.map((x) => x - 1);
check(Math.abs(atr(Array(30).fill(101), Array(30).fill(99), Array(30).fill(100)) - 2) < 1e-12, "ATR of constant 2-point range is 2");
let ad = adx(rh, rl, rc);
check(ad.adx === 100 && ad.plus_di === 50 && ad.minus_di === 0 && ad.strength === "trending" && adx(rh.slice(0, 27), rl.slice(0, 27), rc.slice(0, 27)) === null, `ADX steady uptrend (${JSON.stringify(ad)})`);
check(eq(stochastic(rh, rl, rc), { k: Math.round(14 / 15 * 10000) / 100, d: Math.round(14 / 15 * 10000) / 100 }), "stochastic");
let tp = text(await call("analyze_prices", { closes: [...Array(29).fill(100), 105], highs: [...Array(29).fill(101), 110], lows: [...Array(29).fill(99), 100] }));
check(eq(tp.pivots_classic, { P: 105, R1: 110, S1: 100, R2: 115, S2: 95, R3: 120, S3: 90 }), `pivots (${JSON.stringify(tp.pivots_classic)})`);
let sws = swings([1, 2, 5, 2, 1, 2, 6, 2, 1], [1, 2, 5, 2, 1, 2, 6, 2, 1]);
check(eq(sws.highs.map((p) => p.price), [5, 6]) && eq(sws.lows.map((p) => p.price), [1]), "swings");
let fb = fibonacci([150, 120, 100, 140, 200, 180], [150, 120, 100, 140, 200, 180], 180);
check(fb.move === "up" && fb.retracements["61.8%"] === 138.2 && fb.retracements["50%"] === 150 && fb.extensions["161.8%"] === 261.8 && fb.extensions["200%"] === 300 && fb.retraced_so_far === 0.2 && fb.pullback.price === 180 && eq(fb.pullback.projections, { "100%": 280, "127.2%": 307.2, "161.8%": 341.8, "200%": 380 }), `fibonacci (${JSON.stringify(fb.retracements)})`);
const dv = [...Array.from({ length: 20 }, (_, i) => 100 + (i % 2))];
for (let i = 0; i < 8; i++) dv.push(dv.at(-1) - 3);
for (let i = 0; i < 8; i++) dv.push(dv.at(-1) + 2);
while (dv.at(-1) > 78) { const x = dv.at(-1); dv.push(x - 3, x - 1); }
dv.push(dv.at(-1) - 3); dv.push(dv.at(-1) + 3, dv.at(-2) + 6);
let dvg = rsiDivergence(dv, dv, dv);
check(dvg.length === 1 && dvg[0].type === "regular bullish" && dvg[0].points[1].price < dvg[0].points[0].price && dvg[0].points[1].rsi > dvg[0].points[0].rsi, `rsi divergence (${JSON.stringify(dvg)})`);
const days = ["2026-01-05", "2026-01-06", "2026-01-09", "2026-01-12", "2026-01-16", "2026-01-19"];
check(eq(toWeekly(days, [10, 12, 11, 13, 14, 15], [11, 15, 12, 14, 16, 15], [9, 11, 10, 12, 13, 14], [1, 2, 3, 4, 5, 6]),
  { dates: ["2026-01-09", "2026-01-16", "2026-01-19"], closes: [11, 14, 15], highs: [15, 16, 15], lows: [9, 12, 14], volumes: [6, 9, 6] }), "weekly resampling");
e = await call("analyze_prices", { closes: [1, 2], highs: [1, 1.5], lows: [0.5, 1] }); check(e.isError && /low <= close <= high/.test(e.content[0].text), "rejects bad OHLC");
const ex = 700000 * 0.0000307;
check(tradeCosts(360000, 340000).total === Math.round((700 + ex + 0.7 + 54 + (ex + 0.7) * 0.18) * 100) / 100, "delivery costs by hand");
let ps = text(await call("position_size", { capital: 1000000, entry: 1800, stop: 1700, risk_pct: 2, max_position_pct: 100 }));
check(ps.shares === 200 && ps.position_pct_of_capital === 36 && ps.binding_limit === "risk", "fixed fractional worked example");
ps = text(await call("position_size", { capital: 1000000, entry: 1800, stop: 1700, risk_pct: 2 }));
check(ps.shares === 111 && ps.binding_limit === "20% single-stock cap" && eq(ps.limits, { by_risk: 200, by_capital: 555, by_single_stock_cap: 111 }), "single-stock cap binds");
ps = text(await call("position_size", { capital: 500000, entry: 1000, side: "short", atr: 20, atr_multiplier: 1.5, target: 900, max_position_pct: 100 }));
check(ps.stop === 1030 && ps.stop_basis === "entry + 1.5 x ATR" && ps.shares === 166 && ps.reward_to_risk === Math.round(100 / 30 * 100) / 100, "ATR stop, short");
ps = text(await call("position_size", { capital: 1000000, entry: 1800, stop: 1700, risk_pct: 2, max_position_pct: 100, target: 2000, win_rate: 0.45 }));
check(ps.kelly.full === Math.round((0.45 - 0.55 / 2) * 10000) / 10000 && ps.expected_value === Math.round((0.45 * ps.gain_at_target.net - 0.55 * ps.loss_at_stop.net) * 100) / 100, "EV and Kelly");
for (const [args, msg] of [[{ capital: 1e6, entry: 100, stop: 110 }, /below the entry/], [{ capital: 1e6, entry: 100 }, /pass a stop price/], [{ capital: 1000, entry: 5000, stop: 4000 }, /rounds to 0 shares/]]) {
  e = await call("position_size", args); check(e.isError && msg.test(e.content[0].text), `rejects ${JSON.stringify(args)}`);
}

const sd = Array.from({ length: 30 }, (_, i) => `2026-03-${String(i + 1).padStart(2, "0")}`), scl = Array.from({ length: 30 }, (_, i) => 100 + i);
let se = text(await call("analyze_prices", { closes: scl, dates: sd, highs: scl.map((x) => x + 1), lows: scl.map((x) => x - 1), entry_date: "2026-03-11" })).since_entry;
const a14 = atr(scl.map((x) => x + 1), scl.map((x) => x - 1), scl, 14);
check(se.first_bar === "2026-03-11" && se.bars === 20 && se.highest_close === 129 && se.atr_trail["1.5x"] === Math.round((129 - 1.5 * a14) * 100) / 100 && se.chandelier_since_entry === Math.round((130 - 3 * a14) * 100) / 100, `since entry (${JSON.stringify(se)})`);
// token
r = await rpc({ jsonrpc: "2.0", id: 9, method: "ping" }, { env: { MCP_TOKEN: "s3cret" } }); check(r.status === 401, "MCP_TOKEN set: no token -> 401");
r = await rpc({ jsonrpc: "2.0", id: 9, method: "ping" }, { env: { MCP_TOKEN: "s3cret" }, headers: { Authorization: "Bearer s3cret" } }); check(r.status === 200, "MCP_TOKEN set: right token -> 200");
// batch
r = await rpc([{ jsonrpc: "2.0", id: 1, method: "ping" }, { jsonrpc: "2.0", id: 2, method: "ping" }]); j = await r.json(); check(Array.isArray(j) && j.length === 2, "batch");
// old routes untouched
r = await w.fetch(new Request(W + "/"), env); check(r.status === 200 && /custom connector/.test(await r.text()), "root describes the server");
r = await w.fetch(new Request(W + "/pdf?name=w1.pdf&filename=x"), env); check(r.status === 404 || r.status === 200 || r.status === 502, "pdf route answers");
r = await w.fetch(new Request(W + "/pdf?name=../x"), env); check(r.status === 400, "pdf rejects bad names");
import { test } from "node:test";
import assert from "node:assert/strict";
test("worker MCP server", () => assert.deepEqual(fails, []));
