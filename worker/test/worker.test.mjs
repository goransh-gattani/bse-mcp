// Run with:  node --test worker/test/worker.test.mjs   (from the repo root). BSE answers come from fixtures.json.
import w from "../worker.js";
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
check(j.result.tools.length === 8 && j.result.tools.every((t) => t.name && t.description && t.inputSchema.type === "object"), `tools/list (${j.result.tools.map((t) => t.name).join(",")})`);
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
check(f.quarters.map((x) => x.quarter).join(",") === "Q1 FY27,Q4 FY26,Q1 FY26", `financials auto latest + skip unfiled (${f.quarters.map((x) => x.quarter)})`);
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
