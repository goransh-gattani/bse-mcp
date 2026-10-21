---
name: bse-mcp-trading-toolkit
description: "Full analysis of an Indian (NSE/BSE) stock with bse-mcp: trend, levels, indicators, sizing, stops and a buy/sell/hold plan. Use for 'analyze X', 'should I buy X', 'check my position'."
---

# NSE/BSE Trading Toolkit — Orchestrator

This is the master workflow that coordinates 8 specialized trading framework skills for Indian NSE/BSE equities.

## Data (bse-mcp tools)

These skills run on bse-mcp's read-only tools and never place orders. Take indicator values, sizes and costs from the tools rather than estimating them.

| Need | Tool |
|------|------|
| Scrip code from a company name | `search_scrips` |
| Live price, day and 52-week range | `get_quote` |
| Is the price from today's session? | `session` in `get_quote` / `analyze_prices` / `analyze_fundamentals`, or `get_session_status` |
| Indicators on the last 12 months of daily closes | `analyze_prices` with `scripcode`: it fetches BSE's daily closes and volumes itself |
| ATR, ADX, stochastic, chandelier, pivots, high/low swings, or more than a year of history | daily candles passed to `analyze_prices` as `dates`, `closes`, `highs`, `lows`, `volumes`, oldest first |
| Weekly bars | `analyze_prices` with `timeframe="weekly"` |
| Position size, R:R, trading costs | `position_size` |
| Results, margins, valuation | `analyze_fundamentals` |

For daily candles, use NSE's `nse-bhavcopy` MCP server if it's connected (`https://mcp.nseindia.in/bhavcopy/cm/mcp`, no sign-in, about 5 years of end-of-day data by NSE symbol); if a call returns only part of the range, page back until you have 260+ bars. If it isn't connected, work from BSE's closes and tell the user which levels needed highs and lows; they can connect NSE's server or paste candles (a CSV is fine). Never make prices up.

Exchange price histories may not be adjusted for splits and bonuses (NSE's bhavcopy isn't). If `analyze_prices` reports `price_jumps`, check the announcements (`get_announcements`) for a split or bonus before trusting any level that spans the jump.

Say how fresh the price is. BSE quotes every scrip at all times, including after hours, on holidays and for suspended scrips, so `get_quote`, `analyze_prices` with `scripcode` and `analyze_fundamentals` return a `session` block (`get_session_status` gives it alone). Name the time the numbers are from (`data_as_of`). `live`: today's candle is still forming and the indicators run to the previous close. `closed_after_session`: today's close. `pre_open`, `awaiting_open` or `market_closed`: the price is the last close, not live; say so. `stock_not_trading`: the market traded today but this scrip didn't (suspended, halted or no trades); don't present its price as tradable. `unknown`: treat the price as possibly stale.

When you give a verdict on a stock (buy, sell, hold or avoid), record it with `record_analysis`: `skill` is this skill's name (`bse-mcp-trading-toolkit`), with the entry, stop and target you proposed and the number of trading days the call is for (`horizon_days`). The journal is how these skills get judged against what the price did next, so record the call as you stated it, once.

These skills produce a plan for the user to act on. Don't place, change or automate orders; if a broker server that can trade is connected, don't use its order tools from this workflow.

## Master Workflow

Follow this sequence for a full analysis. Skip steps not relevant to the user's question.

```
1. CONTEXT    → What does the user hold? What's their goal?
2. DATA       → get_quote; analyze_prices daily and weekly (scripcode, or candles for ATR-based levels);
                 analyze_fundamentals when results matter
3. STRUCTURE  → Multi-timeframe analysis (→ use bse-mcp-multi-timeframe-analysis skill)
4. TECHNICALS → Chart reading, indicators (→ use bse-mcp-technical-analysis skill)
                 RSI divergences (→ use bse-mcp-rsi-divergence skill)
                 Fibonacci levels (→ use bse-mcp-fibonacci-trading skill)
5. DECISION   → Bias (bullish / bearish / neutral) with the triggers that would confirm or invalidate it
6. SIZING     → How many shares, at what risk: position_size (→ use bse-mcp-position-sizing skill)
7. STOPS      → Initial stop-loss (→ use bse-mcp-stop-loss-strategies skill)
                 Trailing plan (→ use bse-mcp-trailing-stops skill)
8. TARGETS    → R:R ratio check (→ use bse-mcp-risk-reward-ratio skill)
                 Fibonacci extensions (→ use bse-mcp-fibonacci-trading skill)
9. PLAN       → A plan with prices and triggers for the user to decide on
10. RECORD    → record_analysis with the verdict, entry, stop, target and horizon
```

## When to Use Which Skill

| User's Question | Primary Skill | Supporting Skills |
|----------------|---------------|-------------------|
| "Analyze BBTC" | This orchestrator | All 8 as needed |
| "Position size for RELIANCE" | bse-mcp-position-sizing | bse-mcp-stop-loss-strategies, bse-mcp-risk-reward-ratio |
| "Where to set stop-loss?" | bse-mcp-stop-loss-strategies | bse-mcp-technical-analysis (for S/R levels) |
| "RSI divergence on TATAMOTORS?" | bse-mcp-rsi-divergence | bse-mcp-technical-analysis, bse-mcp-fibonacci-trading |
| "Fib levels for INFY" | bse-mcp-fibonacci-trading | bse-mcp-technical-analysis |
| "Should I trail my stop?" | bse-mcp-trailing-stops | — |
| "Is this trade worth taking?" | bse-mcp-risk-reward-ratio | bse-mcp-position-sizing |
| "Weekly vs daily trend?" | bse-mcp-multi-timeframe-analysis | bse-mcp-technical-analysis |

## Output Format

When presenting a full analysis, use this structure:

```markdown
# [STOCK] Analysis — [Date]

Data as of: [session.data_as_of] ([session.status])

## Quick Take
[1-2 sentence summary: bullish/bearish/neutral + key level to watch]

## Position (if held)
[Current holdings, avg price, P&L]

## Technical Setup
[Trend, key levels, indicator readings]

## Scenarios
[Bullish / Bearish / Sideways with probabilities]

## Action Plan
| Action | Trigger | Price | Size | Stop | Target | R:R |
|--------|---------|-------|------|------|--------|-----|

## Risk Summary
- Plan only: the user places any orders with their broker
- Max risk: Rs.XXX (X% of capital)
- Stop-loss: Rs.XXX
- Trailing plan: [method]
```

## Indian Market Notes
- NSE trading hours: 9:15 AM - 3:30 PM IST
- Pre-open session: 9:00 - 9:15 AM
- T+1 settlement
- Price bands: 2%, 5%, 10% or 20% by stock; F&O stocks have no fixed band, only dynamic limits (`get_quote` shows the stock's band)
- STT, exchange charges, stamp duty, brokerage and GST affect actual P&L: a delivery round trip carries 0.2% STT alone (0.1% each side). Use `position_size` for the actual cost of a trade
- BSE-only stocks aren't on NSE's server: use `analyze_prices` with `scripcode`, or ask for candles
- BSE's volumes are its own and usually far below NSE's: compare volume with its own average

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
