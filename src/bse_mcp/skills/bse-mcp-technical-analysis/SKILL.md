---
name: bse-mcp-technical-analysis
description: "Chart reading for NSE/BSE stocks with bse-mcp data: trend, support/resistance, volume, an RSI/MACD/Bollinger/ADX/stochastic dashboard and bull/bear/sideways scenarios."
---

# Technical Analysis

Read the chart systematically — don't cherry-pick indicators that confirm a bias.

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

For this skill: `get_quote` for today's price and range; `analyze_prices` with `scripcode` for the trend, moving averages, RSI, MACD, Bollinger, 52-week position, swings, Fibonacci, divergence and volume; candles with highs and lows for ADX/DI, stochastic and pivots; the same call with `timeframe="weekly"` for the primary trend.

## Step 1: Trend Identification

- **Primary trend** (weekly): Higher highs & higher lows = uptrend. Lower highs & lower lows = downtrend.
- **Secondary trend** (daily): Current swing direction within the primary trend.
- **Moving average alignment**:
  - Price > SMA20 > SMA50 > SMA200 = strong uptrend
  - Price < SMA20 < SMA50 < SMA200 = strong downtrend
  - Mixed = transitional / choppy
- **Cross signals**: Golden cross (SMA50 > SMA200) = bullish. Death cross = bearish.

## Step 2: Support & Resistance

- **Horizontal S/R**: Recent swing highs and lows with at least 2 touches (`swings` in `analyze_prices`)
- **Round numbers**: Psychological levels (Rs.1,000, Rs.1,500, Rs.2,000)
- **Volume clusters**: Zones where heavy trading occurred (act as magnets)
- **Dynamic S/R**: SMA20 (short-term), SMA50 (medium), SMA200 (major)
- **Gap zones**: Unfilled gaps act as support (gap up) or resistance (gap down)

## Step 3: Volume Analysis

| Price Action | Volume | Interpretation |
|-------------|--------|----------------|
| Rising price | Rising volume | Strong move — trend healthy |
| Rising price | Falling volume | Weak rally — suspect, may reverse |
| Falling price | Rising volume | Strong selling — trend acceleration |
| Falling price | Falling volume | Selling exhaustion — bounce possible |
| Spike volume at support | — | Potential capitulation / reversal |
| Spike volume at resistance | — | Breakout attempt or distribution |

Compare current volume to 20-day average (`volume.last_vs_avg_20` in `analyze_prices`). >1.5x = significant.

## Step 4: Indicator Dashboard

Read these from `analyze_prices` (`rsi_14`, `macd`, `bollinger_20_2`, `adx_14`, `stochastic_14_3`):

| Indicator | Bullish | Bearish | Neutral |
|-----------|---------|---------|---------|
| RSI(14) | >50, rising from <30 | <50, falling from >70 | 40-60, flat |
| MACD | Line > Signal, histogram growing | Line < Signal, histogram shrinking | Near zero line |
| Bollinger Bands | Price bouncing off lower band | Price rejected at upper band | Walking the band |
| ADX | >25 with +DI > -DI | >25 with -DI > +DI | <20 (no trend) |
| Stochastic | %K crosses above %D below 20 | %K crosses below %D above 80 | Mid-range |

Count bullish vs bearish signals to gauge overall bias.

## Step 5: Probabilistic Scenarios

Always present 2-3 scenarios with rough probabilities. Assign higher probability to the scenario with more technical evidence.

```
SCENARIO A (Bullish) — XX% probability
- Trigger: [specific price/indicator condition]
- Target: Rs.XXX (nearest resistance / Fib level)
- Invalidation: Close below Rs.XXX

SCENARIO B (Bearish) — XX% probability
- Trigger: [specific condition]
- Target: Rs.XXX (nearest support)
- Invalidation: Close above Rs.XXX

SCENARIO C (Sideways) — XX% probability
- Range: Rs.XXX to Rs.XXX
- Duration estimate: X days/weeks
- Breakout signal: [what to watch]
```

Probabilities should sum to ~100%. Base them on: trend alignment, indicator consensus, volume confirmation, and S/R proximity. They are judgement calls from the evidence, not statistical estimates: say so when presenting them.

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
