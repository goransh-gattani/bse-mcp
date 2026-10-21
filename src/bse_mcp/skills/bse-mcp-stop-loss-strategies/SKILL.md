---
name: bse-mcp-stop-loss-strategies
description: "Choose an initial stop-loss for an NSE/BSE trade: structure, ATR, support or moving-average stops from bse-mcp data, checked against position size and R:R."
---

# Stop-Loss Strategies

A stop-loss is not optional. Every position needs one before entry. The purpose is to cap your maximum loss — not to predict where price will go.

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

For daily candles, use NSE's `nse-bhavcopy` MCP server if it's connected (`https://mcp.nseindia.in/bhavcopy/cm/mcp`, no sign-in, about 5 years of end-of-day data by NSE symbol); if a call returns only part of the range, page back until you have 260+ bars. If it isn't connected, work from BSE's closes and tell the user which levels needed highs and lows; they can connect NSE's server or paste candles (a CSV is fine). Never make prices up.

Exchange price histories may not be adjusted for splits and bonuses (NSE's bhavcopy isn't). If `analyze_prices` reports `price_jumps`, check the announcements (`get_announcements`) for a split or bonus before trusting any level that spans the jump.

Say how fresh the price is. BSE quotes every scrip at all times, including after hours, on holidays and for suspended scrips, so `get_quote`, `analyze_prices` with `scripcode` and `analyze_fundamentals` return a `session` block (`get_session_status` gives it alone). Name the time the numbers are from (`data_as_of`). `live`: today's candle is still forming and the indicators run to the previous close. `closed_after_session`: today's close. `pre_open`, `awaiting_open` or `market_closed`: the price is the last close, not live; say so. `stock_not_trading`: the market traded today but this scrip didn't (suspended, halted or no trades); don't present its price as tradable. `unknown`: treat the price as possibly stale.

When you give a verdict on a stock (buy, sell, hold or avoid), record it with `record_analysis`: `skill` is this skill's name (`bse-mcp-stop-loss-strategies`), with the entry, stop and target you proposed and the number of trading days the call is for (`horizon_days`). The journal is how these skills get judged against what the price did next, so record the call as you stated it, once.

For this skill: the entry price (known or planned); `analyze_prices` (`scripcode`, or candles for ATR) for recent `swings`, `sma` and `price_vs_sma` and, with highs and lows, `atr_14`; then `position_size` with the chosen stop (or `atr` and `atr_multiplier` for an ATR stop) to check the size and rupee risk. Without highs and lows there is no ATR: use a structure or support stop.

## Stop Type Selection

| Method | Best For | How to Calculate |
|--------|----------|-----------------|
| Structure-based | Swing trades, clear chart patterns | Below recent swing low (long) or above swing high (short) |
| ATR-based | Volatile stocks, no clear structure | Entry - ATR(14) × 1.5 to 2.0 |
| Support/Resistance | Range-bound markets, clear levels | Below key support level + buffer |
| Moving Average | Trend-following trades | Below SMA20 (aggressive) or SMA50 (conservative) |

### Structure-Based (Preferred)
Find the most recent swing low (for longs) that, if broken, would invalidate your trade thesis.
```
Stop = Recent swing low - buffer
Buffer = 0.5% for large-caps, 1% for mid/small-caps
```

### ATR-Based
Adapts to the stock's natural volatility:
```
Stop (long) = Entry - ATR(14) × multiplier
Stop (short) = Entry + ATR(14) × multiplier

Multiplier: 1.5 (tight) to 2.0 (standard) to 2.5 (loose)
```

### Support/Resistance-Based
Place stop just below a confirmed support level:
```
Stop = Support level × (1 - buffer%)
Buffer: 0.5% large-cap, 1.0% mid/small-cap
```
Only use levels with at least 2 historical touches.

### Moving Average-Based
For trend-following positions:
```
Aggressive: Stop below SMA20 (for short-term trends)
Moderate: Stop below SMA50 (for medium-term trends)
Conservative: Stop below SMA200 (for long-term holds)
```
Best when MA is clearly sloping in your direction.

## Buffer Rules

- Round stop to nearest Rs.5 or Rs.10 for cleaner levels
- Use **closing price** as trigger, not intraday wicks (unless day trading)
- Add extra buffer if the stock has a history of stop-hunting wicks
- For illiquid stocks (avg volume < 50K/day), use wider buffers (1.5-2%)

## Hard Rules

These are non-negotiable:

1. **Max loss per trade**: 2% of capital (1% if using leverage)
2. **Never move stop further away** — only tighten or leave unchanged
3. **If stop hits**: exit immediately at next open. No "let me wait for close"
4. **Pre-set the stop**: Decide before entering. Don't adjust based on emotions after entry
5. **No mental stops**: Place an actual stop-loss order with your broker, or set hard price alerts. These tools are read-only and won't place it for you.

## Stop Validation

Before finalizing, check:
- [ ] Is the stop beyond normal noise? (At least 1× ATR away from entry)
- [ ] Does the position size at this stop keep risk within limits? (`position_size` shows which limit binds)
- [ ] Is the R:R ratio still acceptable? (→ check with bse-mcp-risk-reward-ratio skill)
- [ ] Is the stop below a meaningful technical level, not just a round number?

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
