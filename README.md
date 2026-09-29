# Yahoo Fantasy Waiver Assistant

Personal, non-commercial fantasy football analytics project for a single private league.

The assistant uses read-only Yahoo Fantasy Sports data to monitor roster changes, player availability, projections, transactions, FAAB activity, and waiver opportunities. It produces recommendations for one user; it does not execute Yahoo transactions.

## Core workflow

1. Discover waiver and free-agent candidates.
2. Estimate each player's fantasy value and uncertainty.
3. Compare each candidate with the exact roster player they would replace.
4. Estimate waiver demand, likely FAAB price, and the chance the player clears to free agency.
5. Recommend one of: CLAIM, VALUE CLAIM, WAIT FOR FREE AGENCY, or PASS.
6. Re-scan after waivers for useful players dropped by other managers.

Every recommendation should identify:

- Add
- Replace / open roster spot
- Action
- Bid
- Maximum bid
- Expected lineup improvement
- Free-agency probability
- Confidence
- Short rationale

See `docs/waiver-strategy.md` for the decision framework and `docs/data-requirements.md` for required inputs.

## Security

OAuth secrets, access tokens, refresh tokens, private league data, and local caches must never be committed. Use environment variables and local ignored files.
