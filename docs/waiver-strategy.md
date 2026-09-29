# Waiver Decision Framework

## Objective

Maximize expected fantasy points and championship upside through Week 17 subject to roster limits, FAAB, weekly acquisition limits, injuries, uncertainty, and the option to wait for free agency.

The system is not a simple player ranking. It separates player scoring from transaction decisioning.

## 1. Player value

Candidate scoring should consider:

- Expected fantasy points
- Recent actual fantasy points
- Projection surprise: actual minus pregame projection
- Position-specific standardized projection surprise
- Opportunity trend: carries, targets, routes, snaps, red-zone work
- Sustainability: distinguish repeatable opportunity from touchdown or long-play variance
- Points above positional replacement
- Next 3-4 week schedule
- Weeks 15-17 playoff schedule
- Market demand

Initial candidate-score weights:

- 30% expected fantasy-point potential
- 20% opportunity trend
- 15% projection outperformance
- 15% points above replacement
- 10% next 3-4 week schedule
- 5% playoff schedule
- 5% market demand

The weighted score surfaces candidates. It does not directly determine the transaction.

## 2. Uncertainty

Adjust confidence for:

- Small sample size
- Projection uncertainty
- Injury uncertainty
- Role-change uncertainty
- Early-season defensive matchup noise

Projection-surprise analysis should be normalized primarily within position and, where practical, comparable expectation/workload buckets.

## 3. Roster impact

Every candidate must be compared with the exact player or open spot they would replace.

Evaluate:

- Incremental expected points
- Probability the pickup enters the starting lineup
- Bench upside / asymmetric ceiling
- Positional scarcity
- Value of preserving an open roster spot
- Opportunity cost of using one of the weekly acquisitions

A technically positive upgrade is not automatically worth making.

## 4. Acquisition strategy

For each candidate estimate:

- Probability another manager claims the player
- Probability the player clears waivers to free agency
- Expected winning FAAB
- Maximum economically justified FAAB
- Opponent roster needs
- Opponent remaining FAAB
- Opponent bidding tendencies
- Value of waiting

Use league-specific transaction history instead of generic FAAB advice whenever enough data exists.

## 5. Overrides

Breaking information can supersede historical scoring:

- Injury to player or teammate
- Starter promotion or demotion
- Depth-chart change
- Major usage change
- Suspension / return
- Post-waiver roster cuts

## 6. Decision states

- CLAIM — meaningful upgrade and material risk the player disappears
- VALUE CLAIM — worthwhile pickup at a low protective bid
- WAIT FOR FREE AGENCY — useful player but likely to clear
- PASS — insufficient roster improvement or poor economics

## 7. Required recommendation output

Every recommendation must include:

- Add: Player X
- Replace: Player Y or Open Spot
- Action: CLAIM / VALUE CLAIM / WAIT FOR FREE AGENCY / PASS
- Bid: $X
- Max bid: $Y
- Expected lineup improvement: +Z points/week
- Free-agency probability: X%
- Confidence: High / Medium / Low
- Reason: concise explanation

## 8. Important modeling rules

- Do not let draft capital permanently protect an underperforming player.
- Do not chase one-game touchdown spikes without opportunity support.
- Do not over-weight schedule; use it as a modifier.
- Use position-specific matchup strength, not generic "bad defense" labels.
- Preserve FAAB and roster flexibility when an upgrade is marginal.
- Re-scan immediately after waivers for useful players dropped by other teams.
