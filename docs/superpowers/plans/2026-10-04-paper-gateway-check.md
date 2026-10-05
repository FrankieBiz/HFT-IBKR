# Paper Gateway Check Implementation Plan

**Goal:** Give the user a bounded, non-ordering official-SDK connection diagnostic.

**Architecture:** Standalone script with optional SDK in isolated child; the parent
validates endpoint and explicit attestations, enforces a total deadline, and prints
only sanitized connection evidence. No changes to offline execution controls.

**Tech Stack:** Python standard library, optional official IBKR Python API.

1. Create `tests/test_paper_gateway.py`; run focused tests and confirm missing-feature
   failure. Cover confirmation/endpoint gates, callback evidence, timeouts, privacy,
   cleanup and malformed child responses.
2. Create `scripts/check_paper_gateway.py` implementing only validation, bounded
   child orchestration and `connect/run/disconnect` with nextValidId evidence.
3. Inspect the official SDK setup/callback definitions without installing it into
   the core environment. Write `docs/operations/paper-gateway-setup.md` for an
   isolated virtual environment and official source installation. Link README.
4. Run focused tests, `make check build demo`, independent review, and fix issues.
   Commit and push on the authorized feature branch. Do not contact a broker.
5. Give the user the pull/install/check command and request the sanitized output.
   Live or paper-order operation remains outside this diagnostic.

## Verification record

Spec/plan review approved with requirements for child confirmation checks, strict
result schema and total process deadlines. Independent implementation review
identified a direct-worker timeout gap; watchdog and failing-then-passing regression
test resolved it. Nine focused diagnostic tests pass. Official ibapi 10.50.2 and
protobuf 5.29.5 install/import plus actual decoder callback were checked under Python
3.14 with transport patched out. No broker connection was attempted. Full check,
build and synthetic demo evidence is in .research-output/gateway-check-verification.log.
