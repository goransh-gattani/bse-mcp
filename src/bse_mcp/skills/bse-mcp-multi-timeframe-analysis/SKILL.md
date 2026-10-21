---
name: bse-mcp-multi-timeframe-analysis
description: "Weekly-then-daily (3-screen) analysis of an NSE/BSE stock with bse-mcp: weekly bias, daily setup, entry trigger and a confluence score. Use for weekly vs daily trend questions."
---

# Multi-Timeframe Analysis

Higher timeframes set the direction. Lower timeframes refine the entry. Never trade against the higher timeframe trend unless you have very strong reasons.

## The 3-Screen Method

| Screen | Timeframe | Purpose | What to Look For |
|--------|-----------|---------|-----------------|
| Screen 1 | **Weekly** | Trend bias | Primary trend, major S/R, 200-week MA |
| Screen 2 | **Daily** | Setup | Pattern formation, indicator signals, entry zone |
| Screen 3 | **4H / 1H** | Entry timing | Precise entry price, tight stop placement (needs intraday candles: see Data) |

### How to use it:
1. **Weekly decides direction** — only take trades in the weekly trend's direction
2. **Daily identifies the setup** — pullback to support in uptrend, rally to resistance in downtrend
3. **Hourly/4H times the entry** — wait for the lower TF to confirm reversal in your direction

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

When you give a verdict on a stock (buy, sell, hold or avoid), record it with `record_analysis`: `skill` is this skill's name (`bse-mcp-multi-timeframe-analysis`), with the entry, stop and target you proposed and the number of trading days the call is for (`horizon_days`). The journal is how these skills get judged against what the price did next, so record the call as you stated it, once.

For this skill:
```
Weekly:  analyze_prices(scripcode=..., timeframe="weekly")   # about 52 weekly bars: 20- and 50-week SMAs, weekly RSI
Daily:   analyze_prices(scripcode=...)                        # about 250 daily bars
Hourly:  not available: BSE's and NSE's free data are end-of-day
```
The 200-week SMA needs about 4 years of daily candles (NSE's server keeps about 5). Without intraday candles, run Screens 1 and 2 and replace Screen 3 with a daily-close trigger (a close back above the swing level, or the daily RSI or MACD turning). Tell the user Screen 3 was done on daily data, and why.

## Screen 1: Weekly Analysis

Check these on the weekly chart:
- **Trend**: Series of higher highs/lows (up) or lower highs/lows (down)?
- **Position vs MAs**: Price relative to 20W and 50W SMA
- **RSI(14) weekly**: Above 50 = bullish bias, below 50 = bearish bias
- **Major S/R**: Horizontal levels with multiple weekly touches
- **Volume trend**: Rising into the trend direction = healthy

**Weekly verdict:** Bullish / Bearish / Neutral — this sets your trading bias.

## Screen 2: Daily Analysis

With the weekly bias established:
- **Look for setups that align**: Pullbacks to buy in uptrend, rallies to sell in downtrend
- **Pattern identification**: Flags, wedges, double bottoms/tops, breakouts
- **Indicator signals**: RSI, MACD, Bollinger on daily
- **Volume**: Confirmation of the setup (declining volume on pullback = healthy)

**Daily verdict:** Setup present / No setup / Counter-trend setup (risky)

## Screen 3: Entry Timeframe (4H / 1H, or a daily trigger)

Once weekly bias + daily setup align:
- **Wait for lower TF confirmation**: A candlestick reversal pattern, RSI bounce, or MACD cross
- **Place entry**: At the confirmation signal
- **Set stop**: Based on lower TF structure (tighter = better R:R)
- **Target**: From daily/weekly levels

## Confluence Scoring

Award 1 point for each alignment. This keeps you honest about setup quality.

| Factor | Point |
|--------|-------|
| Weekly trend agrees with trade direction | +1 |
| Daily shows valid setup pattern | +1 |
| RSI supports on daily timeframe | +1 |
| MACD supports on daily timeframe | +1 |
| Key S/R level provides clear stop or target | +1 |
| Volume confirms the move | +1 |

| Score | Action |
|-------|--------|
| 5-6 | Strong setup — full position size |
| 4 | Good setup — full position size |
| 3 | Marginal — half position size |
| 2 | Weak — skip or paper trade only |
| 0-1 | No setup — do not trade |

## Common Mistakes

- **Trading against the weekly trend** hoping for a reversal — the weekly trend wins most of the time
- **Using only one timeframe** — you miss context and enter with poor timing
- **Forcing alignment** — if timeframes disagree, the answer is "no trade" not "trade anyway"

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
