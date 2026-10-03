---
name: quant-trading-system
description: Research, design, or implement components of this repository's quantitative trading system, from data and backtesting through broker integration and risk controls.
---

# Quant Trading System Work

Use this skill for work based on the repository architecture plan. Read the relevant sections of `docs/plans/optimize-quant-trading-system.md` before making design decisions. The plan is aspirational and contains claims that may become stale or may need correction; it is not implementation authorization or a validated specification.

## Research and design

- Verify broker/API limits, market data rules, infrastructure pricing and latency, authentication behavior, and applicable regulations with current primary sources before relying on them. Include source links and verification dates in design notes.
- Separate measured facts, assumptions, and proposed targets. Do not present vendor latency or uptime claims as guarantees for this system.
- State data provenance, timestamp conventions, adjustment policy, survivorship considerations, and known gaps for market datasets.
- Evaluate strategies out of sample with time-aware validation. Prevent label overlap and look-ahead leakage; account for multiple trials and selection bias. Include commissions, fees, spread, slippage, market impact, and capacity assumptions in performance estimates.

## Engineering and safety

- Keep strategy research and model-assisted coding outside the deterministic order execution and risk path. AI output is a proposal that requires review and reproducible validation.
- Keep historical data, simulation, paper trading, and live trading modes explicit and difficult to confuse. Default new functionality to offline or paper mode.
- Put independent, fail-closed risk checks between strategy signals and broker order submission. Reconcile broker positions and open orders after disconnects before resuming.
- Make order handling idempotent where possible; define behavior for partial fills, duplicate events, timeouts, stale data, rate limits, and reconnects.
- Never commit secrets, account identifiers, or production credentials. Do not access broker accounts, send orders, deploy, or incur expenses unless the user explicitly authorizes the specific action.
- Do not claim a strategy is profitable, statistically proven, or production-ready based only on a backtest or passing software checks.

## Reporting

Summarize changed components, assumptions, evidence, and remaining uncertainty. Distinguish software verification from strategy validation and operational readiness.
