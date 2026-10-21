---
name: bse-mcp-rsi-divergence
description: "Find and grade RSI divergences (regular and hidden) on NSE/BSE stocks from bse-mcp's swing and RSI data, with confirmation rules, stops and targets."
---

# RSI Divergence

Divergences signal that momentum is fading — price is moving one way but the engine (RSI) is losing steam. They're early warnings, not guarantees.

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

For this skill: `analyze_prices` on 120+ daily bars (`scripcode` gives about 250). Its `rsi_divergence` compares the last two swing lows (highs) with RSI(14) at those bars and reports regular or hidden divergence with the points. `swings` lists the recent swing highs and lows with RSI(14) at each, so you can check a third swing for 3-point divergence. Swings come from closes unless highs and lows are given.

## Regular Divergence (Reversal Signal)

Regular divergence suggests the current trend may be exhausting.

| Type | Price Makes | RSI Makes | Meaning |
|------|-----------|-----------|---------|
| **Bullish** | Lower low | Higher low | Selling pressure fading — potential bottom |
| **Bearish** | Higher high | Lower high | Buying pressure fading — potential top |

### How to Identify
1. Find the last 2-3 swing lows (for bullish) or swing highs (for bearish) on the price chart
2. Mark the corresponding RSI values at those same candles
3. If price makes a new extreme but RSI doesn't — that's divergence

### Strength Grading
| Signal | Strength |
|--------|----------|
| 2-point divergence (2 swings) | Standard |
| 3-point divergence (3 swings) | Strong |
| Divergence + oversold/overbought RSI | Stronger |
| Divergence + volume decline | Strongest |

## Hidden Divergence (Continuation Signal)

Hidden divergence suggests the existing trend will continue after a pullback.

| Type | Price Makes | RSI Makes | Meaning |
|------|-----------|-----------|---------|
| **Bullish** | Higher low | Lower low | Uptrend healthy — pullback is a buying opportunity |
| **Bearish** | Lower high | Higher high | Downtrend healthy — rally is a selling opportunity |

Hidden divergence is often overlooked but very powerful in trending markets.

## Trading Divergences

### Entry Strategy
1. **Identify the divergence** on daily chart
2. **Wait for confirmation** — do NOT enter on divergence alone
   - Price breaks above the minor trendline connecting the swing points
   - RSI crosses above 30 (bullish) or below 70 (bearish)
   - A bullish/bearish engulfing candle at the divergence point
3. **Enter** on the close of the confirmation candle
4. **Stop-loss**: Below the divergence low (bullish) or above the divergence high (bearish)
5. **Target**: Previous swing high/low (`swings`), or Fibonacci levels (`fibonacci` in `analyze_prices`) (→ bse-mcp-fibonacci-trading skill)

### Risk Management
```
Entry: Confirmation candle close
Stop: 1% below the divergence swing low (size it with `position_size`)
Target 1: Previous swing high (conservative)
Target 2: Fibonacci extension 127.2% (moderate)
Target 3: Fibonacci extension 161.8% (aggressive)
```

## Important Caveats

- **Divergence can persist**: In strong trends, you can see multiple divergences before price actually reverses. This is why confirmation is mandatory.
- **Timeframe matters**: Daily divergences are more reliable than hourly. Weekly divergences are the most significant.
- **Not standalone**: Always combine with other evidence (S/R levels, volume, trend analysis). Divergence is one input, not the whole thesis.
- **False divergences**: If the RSI is in the 40-60 neutral zone, divergence signals are less meaningful. Best signals come from oversold (<30) or overbought (>70) zones.

## Quick Reference

```
Bullish regular:  Price ↓↓  RSI ↗  → Potential reversal UP
Bearish regular:  Price ↑↑  RSI ↘  → Potential reversal DOWN
Bullish hidden:   Price ↗   RSI ↓↓ → Trend continues UP
Bearish hidden:   Price ↘   RSI ↑↑ → Trend continues DOWN
```

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
