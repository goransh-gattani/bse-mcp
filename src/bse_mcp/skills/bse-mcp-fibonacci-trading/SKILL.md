---
name: bse-mcp-fibonacci-trading
description: "Fibonacci retracements, extensions and pullback targets for NSE/BSE stocks from bse-mcp's swing data: entry zones, targets and confluence with support and moving averages."
---

# Fibonacci Trading

Fibonacci levels identify high-probability zones where price tends to react — for entries on pullbacks and targets on extensions.

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

When you give a verdict on a stock (buy, sell, hold or avoid), record it with `record_analysis`: `skill` is this skill's name (`bse-mcp-fibonacci-trading`), with the entry, stop and target you proposed and the number of trading days the call is for (`horizon_days`). The journal is how these skills get judged against what the price did next, so record the call as you stated it, once.

For this skill: `analyze_prices` returns `fibonacci` from the highest high and lowest low of the last 126 daily bars (52 weekly; closes when no highs and lows are given): the move's direction and swing points, the 23.6-78.6% retracements, extensions measured from the start of the move, and, once a pullback has begun, `pullback.projections`: point C + the move x 100/127.2/161.8/200%, the convention below. For a different swing, take its high and low from `swings` or the user: retracement level = high - (high - low) x ratio.

## Retracement Levels (Entry Zones)

After a significant move up, price often pulls back to these levels before continuing:

| Level | Character | Trading Implication |
|-------|-----------|-------------------|
| 23.6% | Shallow pullback | Strong trend — buyers eager, enter aggressively |
| 38.2% | Normal pullback | Healthy trend — standard entry zone |
| 50.0% | Deep pullback | Trend weakening but viable — enter with caution |
| 61.8% | Golden ratio | Last stand for the trend — high reward if it holds |
| 78.6% | Very deep | Trend likely failed — avoid or use tight stop |

### For downtrend retracements (price bouncing up):
Same levels but inverted — measure from swing high down to swing low.

## Extension Levels (Profit Targets)

After a retracement completes and price resumes the trend:

| Level | Use |
|-------|-----|
| 100% | Measured move — equal to the prior swing |
| 127.2% | Conservative target — good for partial profit |
| 161.8% | Standard target — most common for swing trades |
| 200.0% | Extended target — for strong trends |
| 261.8% | Full extension — rare, only in powerful moves |

### Calculating Extensions
For an uptrend that resumed from point C (the retracement low), targets are C + (swing high − swing low) × 1.272, 1.618 and 2.0. `analyze_prices` gives these as `fibonacci.pullback.projections`.

## How to Draw Fibs

1. **Identify the swing**: Find the most recent significant high and low (at least 5% move)
2. **Direction matters**:
   - Uptrend retracement: Anchor at swing low, drag to swing high
   - Downtrend retracement: Anchor at swing high, drag to swing low
3. **Use the right swing**: The most recent *completed* swing, not one still in progress
4. **Multiple swings**: You can draw Fibs from different timeframes. When levels from different swings overlap, that's a confluence zone (very strong).

## Confluence Zones

The most powerful Fibonacci levels are where they align with other technical factors. These zones have the highest probability of price reaction.

| Confluence Combination | Strength |
|-----------------------|----------|
| Fib level alone | Moderate |
| Fib + horizontal S/R | Strong |
| Fib + moving average (SMA50/200) | Strong |
| Fib + trendline | Strong |
| Fib + S/R + MA | Very strong |
| Fib from multiple timeframes overlapping | Very strong |

### Practical Examples
- Fib 38.2% from daily swing aligns with SMA50 → strong buy zone
- Fib 61.8% from weekly swing aligns with horizontal support from 3 months ago → high-probability entry
- Fib extension 161.8% aligns with a round number (Rs.2,000) → likely profit target

## Fibonacci Trading Rules

1. **Don't use Fibs in isolation** — they work best as confirmation alongside S/R, volume, and indicators
2. **Zone, not line** — treat each level as a zone (±1-2%), not a precise price
3. **Wait for reaction** — don't blindly buy at a Fib level. Wait for a reversal candle (hammer, engulfing, etc.)
4. **Strongest entries**: Fib 38.2% to 61.8% zone in a healthy trend with volume confirmation
5. **If 78.6% breaks**: The trend is likely over — exit or reverse

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
