# ReferralOps MVP — Validation Report

**Run date:** 12 October 2026  
**Scope:** Local prototype with synthetic records only.

## Checks completed

- `python -m compileall -q app tests` — passed.
- `python -m pytest -q` — **19 passed**.
- Extracted dashboard JavaScript and checked it with `node --check` — passed.
- Parsed `n8n/referral_intake_workflow.json` as JSON — passed.
- Started a live local Uvicorn HTTP server and verified `/health`, `/api/v1/profiles`, `/openapi.json`, referral creation, admin lead retrieval, consent rejection, duplicate attribution handling, KPI totals, approval snapshot persistence, reanalysis approval reset, and contact opt-out — passed.

## Important tests represented in the suite

- Referral with no share/processing consent is rejected before storage.
- Duplicate referral attempts retain attribution history and the public intake response hides contact details.
- Repeated idempotency keys replay the same submission; changed payloads under the same key return a conflict.
- Lead scoring is deterministic and profile-driven.
- AI provider failures and obvious unsupported project claims send the lead to manual review without losing the lead record.
- Contact consent is required before follow-up approval; opt-out withdraws permission and holds an approved draft.
- Re-analysis resets a prior approval; the approved draft snapshot and hash are traceable in the audit history.
- Site-visit transitions and commission eligibility gates are enforced; no payment endpoint exists.
- Unknown/misconfigured AI provider names do not silently fall back to demo mode.

## Not verified / intentionally out of scope

- A live OpenAI request was not made because no API key was provided. The adapter is implemented using the documented structured-output format, but a real provider request still needs to be tested with an authorised key and synthetic data.
- The n8n workflow file parsed as JSON but was not imported or executed in an n8n runtime. Its URL must be changed to match the actual host/network topology.
- No company CRM, production contact channel, calendar, payment provider, or live Lakhotia system is connected.
- The dashboard was syntax-checked and its APIs were smoke-tested; this validation did not run a full browser automation suite across desktop and mobile browsers.
- The referral partner registry, scoring weights, status thresholds, consent language, and commission milestone are demo assumptions, not approved company policy.

## Reproduction

```bash
python -m compileall -q app tests
python -m pytest -q
```

The application is a local demo; do not expose it publicly without replacing the demo authentication, consent capture, rate limiting, data-retention controls and operational policies.
