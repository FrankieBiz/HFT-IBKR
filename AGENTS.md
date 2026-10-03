# HFT Repository Guidance

This repository starts with an architecture plan, not an implemented trading system. Treat `docs/plans/optimize-quant-trading-system.md` as a proposal and source of requirements, not as verified technical, broker, legal, or financial guidance.

Before implementing any part of the plan:

- Read the relevant plan sections and the repository's quant-trading skill at `.agents/skills/quant-trading-system/SKILL.md`.
- Verify time-sensitive broker limits, API behavior, costs, authentication requirements, infrastructure claims, and regulatory obligations against current primary sources. Record sources and dates for decisions.
- Keep research, simulation, paper trading, and live execution clearly separated. Never enable live order submission, handle credentials, deploy infrastructure, incur costs, or contact external services without explicit user authorization for that action.
- Design fail-closed risk controls and broker-state reconciliation before any execution path. Treat paper results as unproven until realistic fees, slippage, market impact, and data quality are modeled.
- Prefer small, reviewable changes. Describe assumptions and validation performed; do not imply profitability or production readiness from a successful build or backtest.

Follow any more specific instructions in subdirectories when they apply.
