
---

## Planned Features

### News Intelligence Layer (Phase 2)
A hybrid system combining pure arbitrage math with web search signals to manage positions dynamically.

**Concept:**
- Web search monitors news for each open position (30% weight alongside arb math)
- High-confidence signals trigger position reassessment
- Bot can close early, flip sides, or increase exposure based on real-world events

**Where it adds value:**
- Early exit signals (candidate disqualified, election postponed)
- New opportunity detection (breaking news causes price dislocations)
- Position sizing (reduce exposure in high-uncertainty markets)
- Risk flags (market restructured or cancelled)

**Guardrails required:**
- Minimum signal strength threshold (filter noise)
- Cooldown period (don't react to same story twice)
- Position age check (ignore short-term noise on long-dated positions)
- Human confirmation for large position changes

**Implementation phases:**
1. News monitoring — alerts only, no auto-action
2. Auto-action on high-confidence signals with human approval
3. Full autonomous execution with guardrails

