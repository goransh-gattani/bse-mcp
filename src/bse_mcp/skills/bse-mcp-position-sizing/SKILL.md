---
name: bse-mcp-position-sizing
description: "How many shares to buy: fixed-fractional, ATR and Kelly sizing with Indian trading costs and portfolio limits, computed by bse-mcp's position_size tool."
---

# Position Sizing

Position sizing is how you survive. The goal: risk a small, consistent percentage of capital per trade so that no single loss can cripple your account.

## Data (bse-mcp tools)

Compute every size with `position_size` (bse-mcp) rather than by hand. It applies the methods below, caps the result by capital (with leverage) and the single-stock limit, says which limit decided the size, and nets out Indian trading costs. These tools are read-only and never place orders.

1. **Account size**: total trading capital (ask the user if not known)
2. **Current price**: `get_quote`, or user-provided
3. **ATR(14)**: `analyze_prices` on 60+ daily candles with highs and lows (e.g. from NSE's `nse-bhavcopy` MCP server). BSE's daily closes alone don't give ATR: without candles, size from a structure stop at a recent swing low (`swings`) instead.
4. **Existing positions**: ask the user (needed for the sector and open-risk limits below)

## Method 1: Fixed Fractional (Default)

This is the go-to method. Simple, robust, works for everyone.

```
Risk per trade = Account size × Risk%
Shares = Risk per trade ÷ (Entry price - Stop-loss price)
Capital required = Shares × Entry price
```

**Risk% guidelines:**
| Situation | Risk% |
|-----------|-------|
| Normal (no leverage) | 1-2% |
| With 2x leverage | 0.5-1% |
| With 3-4x leverage | 0.25-0.5% |
| High conviction trade | Up to 3% (rare) |
| New/uncertain setup | 0.5% |

### Example
```
Account: Rs.10,00,000
Risk: 2% = Rs.20,000
Entry: Rs.1,800
Stop: Rs.1,700 (Rs.100 risk per share)
Shares: 20,000 ÷ 100 = 200 shares
Capital: 200 × 1,800 = Rs.3,60,000 (36% of account)
```
36% of the account breaks the 20% single-stock limit under Portfolio Constraints below. With that limit applied, `position_size` gives 111 shares (Rs.1,99,800) and reports the single-stock cap as the binding limit. Always apply the constraints.

## Method 2: ATR-Based Sizing

Uses volatility to set the stop distance, then sizes accordingly.

```
Stop distance = ATR(14) × multiplier
Shares = Risk amount ÷ Stop distance
```

| Market Condition | ATR Multiplier |
|-----------------|----------------|
| Range-bound or weak trend (ADX < 20) | 1.5× ATR |
| Normal | 2.0× ATR |
| Strong trend (ADX > 30) | 2.5× ATR |

ATR already scales the stop to the stock's volatility; ADX measures trend strength, and the multiplier sets how much room the trade gets.

This naturally sizes you smaller in volatile stocks and larger in calm ones.

## Method 3: Kelly Criterion (Advanced)

For traders with a track record of at least 30 trades:

```
Kelly% = W - (1 - W) / R
W = historical win rate
R = average win / average loss

Use Half-Kelly (Kelly% ÷ 2) for real trading — full Kelly is too aggressive.
```

| Win Rate | Avg W/L Ratio | Kelly% | Half-Kelly |
|----------|---------------|--------|------------|
| 40% | 2.0 | 10% | 5% |
| 50% | 1.5 | 17% | 8% |
| 60% | 1.2 | 27% | 13% |

## Portfolio Constraints

These are hard limits — never exceed them regardless of sizing method:

| Constraint | Limit |
|-----------|-------|
| Single stock | Max 20% of portfolio |
| Single sector | Max 35% of portfolio |
| Total open risk | Max 6% of portfolio (sum of all position risks) |
| Correlated positions | Max 3 stocks in same sector simultaneously |

If a position would breach a constraint, reduce size until it fits.

## Leverage Adjustment

With fixed-fractional sizing the planned loss at the stop doesn't change with leverage: leverage only lets the position grow beyond your capital (`position_size` caps it at capital × leverage). The danger is a gap through the stop, which takes more of your capital the larger the position is. So reduce your base risk% by dividing it by the leverage:

```
At 3.74x leverage:
  Normal risk: 2%
  Adjusted risk: 2% ÷ 3.74 ≈ 0.5%
```

## Output

Present position sizing as:
```
Position Size: XXX shares
Capital Required: Rs.X,XX,XXX
Risk Amount: Rs.X,XXX (X.X% of account)
Stop-Loss: Rs.XXX (X.X% below entry)
Portfolio Allocation: XX% of total capital
```

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
