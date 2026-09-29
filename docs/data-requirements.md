# Data Requirements

## Yahoo / league data

Collect and retain, where the API permits:

- League settings and scoring rules
- Current team roster and roster slots
- IR status
- Available players and waiver/free-agent status
- Current FAAB budget
- Weekly acquisition count and limit
- Opponent rosters
- Opponent remaining FAAB
- League transaction history
- Winning waiver bids
- Losing bids when exposed by Yahoo
- Players dropped during waiver processing

## Weekly player data

Snapshot before each game or scoring period:

- Yahoo pregame projected fantasy points
- Actual fantasy points
- Position
- Team
- Opponent
- Availability status

Retaining historical pregame projections is important because projections may change after games are played.

## Opportunity data

When available from reliable sources:

- Carries
- Targets
- Receptions
- Routes run
- Snap share
- Red-zone carries
- Red-zone targets
- Touches
- Starting / depth-chart role

## Schedule data

For each player:

- Next 3-4 opponents
- Weeks 15-17 opponents
- Position-specific fantasy points allowed by each defense
- Prefer opponent-adjusted measures when practical

Schedule should be a modifier rather than the primary driver.

## Derived metrics

Compute deterministically:

- Projection error = actual - pregame projection
- Position-specific projection-error z-score
- Rolling 2-, 3-, and 4-game projection surprise
- Expected fantasy-point level
- Opportunity trend
- Points above positional replacement
- Estimated lineup-start probability
- Incremental value versus exact roster replacement
- Claim probability
- Free-agency clearance probability
- Expected winning FAAB
- Maximum justified FAAB
- Confidence / uncertainty

## Storage

Do not commit private league data or OAuth credentials.

Historical projections, transactions, and model outputs should be stored locally or in a private data store once the application is deployed.
