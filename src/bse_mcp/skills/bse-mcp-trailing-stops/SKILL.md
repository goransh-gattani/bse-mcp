---
name: bse-mcp-trailing-stops
description: "Trail the stop on an open NSE/BSE position with bse-mcp: breakeven at 1R, ATR trail, chandelier exit, swing-low and moving-average trails measured from your entry date."
---

# Trailing Stops

Once a trade is profitable, trailing stops protect your gains while letting winners run.

## Data (bse-mcp tools)

These skills run on bse-mcp's read-only tools and never place orders. Take indicator values, sizes and costs from the tools rather than estimating them.

| Need | Tool |
|------|------|
| Scrip code from a company name | `search_scrips` |
| Live price, day and 52-week range | `get_quote` |
| Indicators on the last 12 months of daily closes | `analyze_prices` with `scripcode`: it fetches BSE's daily closes and volumes itself |
| ATR, ADX, stochastic, chandelier, pivots, high/low swings, or more than a year of history | daily candles passed to `analyze_prices` as `dates`, `closes`, `highs`, `lows`, `volumes`, oldest first |
| Weekly bars | `analyze_prices` with `timeframe="weekly"` |
| Position size, R:R, trading costs | `position_size` |

For daily candles, use NSE's `nse-bhavcopy` MCP server if it's connected (`https://mcp.nseindia.in/bhavcopy/cm/mcp`, no sign-in, about 5 years of end-of-day data by NSE symbol); if a call returns only part of the range, page back until you have 260+ bars. If it isn't connected, work from BSE's closes and tell the user which levels needed highs and lows; they can connect NSE's server or paste candles (a CSV is fine). Never make prices up.

Exchange price histories may not be adjusted for splits and bonuses (NSE's bhavcopy isn't). If `analyze_prices` reports `price_jumps`, check the announcements (`get_announcements`) for a split or bonus before trusting any level that spans the jump.

For this skill: entry price, entry date and the original stop from the user (1R = entry - original stop); `get_quote` for the current price; `analyze_prices` with `entry_date` (and `side`), using `scripcode` when the entry is within the last 12 months, otherwise candles from before the entry. Its `since_entry` gives the highest close and high since entry and `structure_trail` (the latest swing low since entry); with highs and lows also `atr_trail` at 1.5x/2x/3x ATR(14) and `chandelier_since_entry` (highest high - 3 x ATR(14), as defined below). `sma` and `ema` give the MA-trail levels (SMA20, EMA50, SMA200).

## The Hybrid Approach (Recommended)

This progressive system adapts as the trade matures:

| Trade Stage | Profit Level | Trailing Method |
|------------|-------------|-----------------|
| Just entered | 0 to 1R | **Fixed stop** — don't trail yet, use initial stop-loss |
| Early profit | 1R gained | **Move to breakeven** — stop at entry price (eliminates risk) |
| Building profit | 2R gained | **ATR trail** — highest close minus ATR(14) × 1.5 |
| Strong runner | 3R+ gained | **Structure trail** — below most recent swing low |

This works because:
- Below 1R: Moving stop too early gets you shaken out on noise
- At 1R: Breakeven means you can't lose money — psychological freedom to hold
- At 2R: ATR trail gives the stock room to breathe while protecting most profit
- At 3R+: Structure trail is tighter, appropriate when you have a large cushion

## Individual Methods

### ATR Trail
```
Trailing stop = Highest close since entry - ATR(14) × multiplier
Multiplier: 1.5 (tight), 2.0 (standard), 3.0 (loose)
```
Recalculate daily at market close. Only move stop up, never down.

### Structure Trail
```
Trailing stop = Below the most recent higher low
```
Identify swing lows on the daily chart. Each new higher low becomes the new stop reference. Best for stocks making clear stair-step patterns.

### Moving Average Trail
```
Aggressive: Trail below SMA20 (for fast trends)
Moderate: Trail below EMA50 (for steady trends)
Conservative: Trail below SMA200 (for long-term holds)
```
Use closing price vs MA — if daily close is below the MA, exit next day.

### Chandelier Exit
```
Trailing stop = Highest high since entry - ATR(14) × 3.0
```
Looser than the standard 2× ATR trail: 3× ATR, measured from the highest high. Good for volatile runners where you want to ride big swings.

## Trailing Stop Rules

1. **Only move up**, never down — a trailing stop is a ratchet
2. **Check daily at market close** — don't adjust intraday (noise)
3. **Use closing prices** for triggers — ignore intraday wicks
4. **When stop is hit**: exit at next day's open, no exceptions
5. **Don't overtighten**: If you're trailing too tight, you'll get stopped out on normal pullbacks. Give the stock room proportional to its ATR.

## Choosing Your Method

| Stock Behavior | Best Trail Method |
|---------------|------------------|
| Strong uptrend, clear swing lows | Structure trail |
| Trending but volatile | ATR trail (2.0×) or Chandelier |
| Steady grinder, low volatility | MA trail (EMA50) |
| Explosive mover, unsure of top | Chandelier exit (3.0× ATR) |
| Long-term investment | MA trail (SMA200) |

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
