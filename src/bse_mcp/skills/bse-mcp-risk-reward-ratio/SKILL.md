---
name: bse-mcp-risk-reward-ratio
description: "Is a trade worth taking? Risk-reward, breakeven win rate, expected value and multi-target R:R for NSE/BSE trades, net of Indian trading costs, via bse-mcp's position_size."
---

# Risk-Reward Ratio

If the math doesn't work, don't take the trade. R:R is the simplest filter that separates good setups from bad ones.

## Data (bse-mcp tools)

This is arithmetic on entry, stop and target: use `position_size` (bse-mcp) rather than computing by hand. With `target` it returns R:R before and after Indian trading costs (STT, exchange charges, stamp duty, GST, and your brokerage if given); with `win_rate` it adds expected value, the breakeven win rate and Kelly fractions. Costs matter: a delivery round trip carries 0.2% STT alone, which visibly lowers R:R on tight setups. These tools are read-only and never place orders.

## Calculation

```
Risk = Entry price - Stop-loss price
Reward = Target price - Entry price
R:R = Reward ÷ Risk

Example:
  Entry: Rs.1,800
  Stop: Rs.1,700 → Risk = Rs.100 per share
  Target: Rs.2,100 → Reward = Rs.300 per share
  R:R = 300 ÷ 100 = 3:1
```

In rupee terms:
```
Total risk = Risk per share × Number of shares
Total reward = Reward per share × Number of shares
```

## Minimum R:R by Win Rate

Your win rate determines the minimum R:R needed to be profitable over time.

| Win Rate | Min R:R (Breakeven) | Recommended Min |
|----------|--------------------|-----------------|
| 30% | 2.33:1 | 3:1 |
| 40% | 1.50:1 | 2:1 |
| 50% | 1.00:1 | 1.5:1 |
| 60% | 0.67:1 | 1:1 |
| 70% | 0.43:1 | 0.75:1 |

Breakeven R:R = (1 − win rate) ÷ win rate, before costs.

If you don't know your win rate, assume 40-50% and require at least 2:1 R:R.

## Trade Filtering Rules

| R:R Ratio | Decision |
|-----------|----------|
| Below 1:1 | **Skip** — you're risking more than you can gain |
| 1:1 to 1.5:1 | Only if win rate > 55% AND high-conviction setup |
| 1.5:1 to 2:1 | Acceptable for experienced traders with edge |
| 2:1 to 3:1 | **Good** — standard for swing trades |
| 3:1+ | **Excellent** — take these trades consistently |

## Multi-Target R:R

For trades with multiple profit targets (scaling out):

```
Target 1 (50% of position): Rs.1,900 → R:R = 1:1
Target 2 (30% of position): Rs.2,000 → R:R = 2:1
Target 3 (20% of position): Rs.2,200 → R:R = 4:1

Weighted R:R = (0.5 × 1) + (0.3 × 2) + (0.2 × 4) = 1.9:1
```

This is useful when you plan to scale out at different levels.

## Expected Value

For a more complete picture, calculate expected value per trade:

```
EV = (Win rate × Average win) - (Loss rate × Average loss)

Example:
  Win rate: 50%, Avg win: Rs.10,000, Avg loss: Rs.5,000
  EV = (0.5 × 10,000) - (0.5 × 5,000) = Rs.2,500 per trade

Positive EV = edge. Negative EV = change your approach. `position_size` computes EV net of costs.
```

## R:R Checklist

Before entering any trade:
- [ ] Have I identified a specific target (not just "it'll go up")?
- [ ] Is the stop-loss at a technically meaningful level?
- [ ] Is R:R at least 1.5:1 (ideally 2:1+)?
- [ ] Does the position size keep risk within 1-2% of capital?
- [ ] If this trade hits stop, will I still be fine psychologically and financially?

---
Adapted from [nse-trading-skills](https://github.com/Bhala-Srinivash/nse-trading-skills) by Bhala Srinivash (MIT licence, see `LICENSE-nse-trading-skills` in this folder) for the read-only [bse-mcp](https://github.com/goransh-gattani/bse-mcp) tools. Educational frameworks, not investment advice.
