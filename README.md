# ReferralOps — Evidence-first Referral & Lead Intelligence Prototype

**Status:** local demonstration MVP. This is not a production CRM or a verified company integration.

ReferralOps demonstrates a connected workflow for an industrial-project referral programme: referral intake, consent gating, partner attribution, duplicate detection, deterministic qualification, optional AI-assisted analysis/drafts, human approval, site-visit state tracking, commission-review gating, audit history and KPI reporting.

## What works in this demo

- FastAPI REST API with interactive OpenAPI docs at `/docs`.
- SQLite persistence using SQLAlchemy sessions and commits.
- Synthetic referral partners `PARTNER-001` and `PARTNER-002` seeded on startup.
- Pydantic validation for request shape, types and bounds.
- Consent-to-share gate checked before persistence.
- Separate contact-consent check before approving a follow-up draft.
- Duplicate detection and referral history; first attribution is not overwritten.
- Optional `Idempotency-Key` handling to stop repeated requests from creating duplicate submissions.
- Deterministic, explainable scoring owned by Python—not the LLM.
- Separate JSON qualification profiles (`industrial_land` and `generic_b2b_demo`) so sector acceptance and thresholds can change without modifying endpoint code.
- Demo analysis mode that works without an external account; optional live OpenAI Chat Completions adapter using structured output and application-level validation.
- Manual follow-up approval, site visit requested/scheduled/completed/cancelled transitions, and commission review state.
- Admin-protected lead listing, details, approvals and KPI routes (`X-Admin-Key`).
- Simple browser dashboard that calls the same REST APIs.
- Tests for consent, duplicates, idempotency, model failure, unsafe output, approval gates, site-visit transitions, commission gates and KPIs.
- Example n8n webhook-to-API workflow under `n8n/`.

## What is deliberately not connected

- No email, phone, WhatsApp or LinkedIn message is sent.
- No real calendar invitation is created.
- No commission payment or transfer is executed.
- No production CRM is connected; use the REST API or a test/sandbox CRM adapter.
- Company plot availability, pricing, approvals, legal status and delivery timelines are not verified by this software.

Those are deliberate boundaries: a working prototype should not pretend an unconfigured external integration succeeded.

## Run locally (Windows PowerShell)

Use Python 3.11+ (tested here with Python 3.13).

```powershell
cd referralops_demo
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open:

- Dashboard: <http://127.0.0.1:8000/>
- API docs: <http://127.0.0.1:8000/docs>
- Health: <http://127.0.0.1:8000/health>

The default local admin key is `demo-admin-key`. It exists only to make local demonstration easy. You can also start it with `run_windows.bat` after dependencies are installed. Set a new random `ADMIN_API_KEY` before any shared deployment. Do not expose this prototype to the public internet as-is.

## Run tests

In the activated virtual environment:

```powershell
pytest -q
```

The tests use temporary SQLite databases and synthetic data. They do not call an external AI provider.

## Optional live OpenAI analysis

Demo mode is the default and is labelled in the dashboard. To call the external API for lead analysis, set the following in `.env`:

```dotenv
AI_PROVIDER=openai
OPENAI_API_KEY=your_real_key_here
OPENAI_MODEL=gpt-4o-mini
OPENAI_TIMEOUT_SECONDS=15
```

Restart the server. The OpenAI adapter uses structured JSON output and Pydantic validation. It sends only qualification fields (industry, requirements, requested area, budget, timeline, decision-maker signal, site-visit interest)—not contact name, email, phone or referral partner identity. Free-text requirements remain untrusted input. API usage may incur provider charges. Keep keys out of source control and logs.

If the external API fails or returns output rejected by the guard, the referral remains persisted and changes to `failed_manual_review`; the app does not silently substitute demo content or send anything externally.

Official implementation references checked during design:

- FastAPI testing with `TestClient` and pytest: <https://fastapi.tiangolo.com/tutorial/testing/>
- SQLAlchemy session and transaction lifecycle: <https://docs.sqlalchemy.org/en/20/orm/session_basics.html>
- OpenAI structured outputs: <https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat>
- n8n HTTP Request node: <https://docs.n8n.io/integrations/builtin/core-nodes/n8n-nodes-base.httprequest/>

## API map

| Method | Endpoint | Purpose | Access |
|---|---|---|---|
| `GET` | `/health` | Basic health | Public |
| `GET` | `/api/v1/config` | Provider mode and safety boundaries | Public |
| `GET` | `/api/v1/profiles` | Available qualification profiles | Public |
| `POST` | `/api/v1/referrals` | Validate and register referral | Partner code + consent gate; demo auth only |
| `GET` | `/api/v1/partners` | List referral partners | Admin key |
| `GET` | `/api/v1/leads` | List leads | Admin key |
| `GET` | `/api/v1/leads/{id}` | Lead passport, referrals, approvals, visits, commission | Admin key |
| `POST` | `/api/v1/leads/{id}/reanalyze` | Re-run AI adapter | Admin key |
| `POST` | `/api/v1/leads/{id}/approval` | Approve/hold/reject follow-up draft | Admin key |
| `POST` | `/api/v1/leads/{id}/site-visits` | Request a site visit | Admin key |
| `PATCH` | `/api/v1/site-visits/{id}` | Schedule/complete/cancel visit | Admin key |
| `POST` | `/api/v1/leads/{id}/commission/check` | Check demo eligibility for human review | Admin key |
| `POST` | `/api/v1/leads/{id}/commission/review` | Record commission decision state | Admin key |
| `GET` | `/api/v1/kpis` | Funnel and reliability KPIs | Admin key |
| `GET` | `/api/v1/audit` | Workflow audit events | Admin key |

For protected calls include `X-Admin-Key: demo-admin-key` (or your configured key).

## Prototype business logic — assumptions to replace after stakeholder review

- Initial target sectors: manufacturing, warehousing and logistics.
- Initial score weights: industry (30), required area (20), budget estimate/scale (20), timeline (0–15), decision authority (0–10), site-visit intent (0–5).
- Missing area, budget or timeline moves the lead to `needs_info`, rather than treating missing data as proof of poor fit.
- `priority_review` begins at score 75; `standard_review` at 50; these thresholds need calibration against labelled examples.
- A completed site visit enables **human commission review eligibility only**, provided attribution is not disputed. The application does not define actual commission rates or payment policy.
- Duplicate detection matches exact normalised email or phone. Company-name similarity is not used to auto-merge records; fuzzy matching should be introduced only as a review flag with evaluation tests.
- Consent booleans are suitable only for a synthetic demo. A production system needs legally reviewed consent wording, source/evidence, notice versioning, withdrawal handling, channel compliance and access controls.

## n8n workflow

Import `n8n/referral_intake_workflow.json` into a local n8n instance. Update the HTTP Request node URL so it can reach this FastAPI process from the n8n runtime. With local Docker, `host.docker.internal` often resolves to the host; otherwise use the correct host/service name. The workflow is an integration starter, not an end-to-end verified deployment. Test it against synthetic data and configure an n8n error workflow and retry policy. Pass a stable idempotency key for webhook retries; never put prospect PII into execution logs unnecessarily.

## Before production

Do not skip the security/legal step. Add real authentication and roles, rate limiting, CSRF/origin considerations for browser sessions, encrypted secrets, retention and deletion rules, consent withdrawal handling, CRM provider sandbox tests, data-processing agreements, monitoring, backups, data migration, load tests, and a review of applicable Indian privacy and commercial-communications requirements. Replace all demo policy with approved business decisions.
