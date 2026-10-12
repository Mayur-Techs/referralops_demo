# Antigravity Task Prompt — Mayur's Matrix360 Shared Lead Database

## Your role and objective

You are working inside the **existing ReferralOps / Matrix360 project workspace**. Implement **Mayur's database-layer responsibility only**, based on `matrix 360.pdf` (Matrix360 · Intern Team · 12 Oct 2026).

**Do not build the complete Matrix360 product now. Do not rebuild the app. Do not replace working code just because you prefer a different design.** First inspect what is already present in this workspace, then make the smallest safe, tested changes needed to make one shared lead database usable by the team.

The intended outcome is simple: a teammate in a different city opens the same hosted application URL, submits a lead through the existing app/API, and the lead is saved once in the central database. Another authorized teammate can then find that same record from their own location. There must not be one database per teammate or a database file shared through Google Drive, OneDrive, email, or a network folder.

## 1. Read the current project before editing anything

Before changing code:

1. Inspect the entire relevant repository structure, README, `.env.example`, dependency files, database setup, models, schemas, API routes, authentication, frontend API calls, AI-provider adapter, and current tests.
2. Identify which database tables and endpoints already exist and what currently creates, reads, updates, and deletes records.
3. Run the current test suite and record the exact baseline result. If tests fail before your changes, record those failures separately; do not claim they were caused or fixed by this task without evidence.
4. Identify existing behaviours other parts of the system depend on, including route paths, JSON field names, authentication headers, status/stage values, database constraints, and response structures.
5. Write a brief implementation plan in your final report before making changes. Then proceed with the implementation; do not stop after writing a plan.

If this workspace differs from the earlier ReferralOps prototype, adapt to the code actually present. Do not assume files or functionality exist until you inspect them.

## 2. Strict scope: what to implement for Mayur

The Matrix360 PDF assigns Mayur the foundation other teammates depend on:

1. Make the existing ReferralOps app the one place every lead is saved.
2. Add/support the shared lead fields so every person's tool sends and receives the same format.
3. Provide a working endpoint for saving a lead and a working endpoint for retrieving/searching leads. Reuse the existing `/api/v1/leads` route if present; do not create a competing API unnecessarily.
4. Preserve the existing duplicate check and ensure it checks in this exact priority order:
   - normalized phone number, comparing the last 10 digits when at least 10 digits are available;
   - normalized email address;
   - normalized LinkedIn profile URL.
5. Keep compatibility with the existing Grok/LLM adapter and current workflows. Do not redesign AI, chat, WhatsApp, Radar, advertisements, site visits, scoring, n8n, or the frontend. Only make a minimal compatibility adjustment if the database/API integration requires it, and test that adjustment.
6. Make the database architecture support a local SQLite demo now and a centrally hosted PostgreSQL database for real multi-location team use without requiring a rewrite of business logic.

**Acceptance condition from the PDF:** another teammate can send a lead to Mayur's app, and the saved lead can be retrieved from the same central system. Mayur can share the hosted app URL and one synthetic example lead with the team.

## 3. Critical protection rules — existing systems must not break

- Do not rewrite the whole project or introduce a new application framework.
- Do not remove or rename existing API routes, request fields, response fields, environment variables, database tables, status values, or auth behaviour without a demonstrated compatibility reason and a migration plan.
- Do not delete the current SQLite database, reset real data, drop tables, run `drop_all`, or create a new empty database that silently replaces the current one.
- Do not perform destructive schema changes. Do not alter history or silently overwrite lead attribution.
- Do not remove duplicate detection, consent checks, opt-out controls, audit history, idempotency support, AI safety validation, human-approval gates, site-visit workflows, commission review, or KPIs if they exist.
- Do not make protected lead data or save/get endpoints public just to make remote access easier.
- Do not expose database credentials, `DATABASE_URL`, API secrets, Grok keys, admin keys, or other secrets in source code, browser JavaScript, logs, screenshots, API responses, Git, or `.env.example` values.
- Do not change other teammates' systems in this task. Keep their integration contracts stable and document exactly how they should connect to this database/API.
- Do not claim PostgreSQL, cloud hosting, Grok, n8n, CRM, or other integrations are live unless you have actually configured and tested them with available credentials/services.
- Make incremental edits. Before each material change, understand what currently calls the affected code. After each logical change, run targeted tests; at the end, run the full existing suite.

## 4. Shared lead format — preserve these exact field names

The Matrix360 PDF states that **every tool uses the same field names**. Preserve the following snake_case keys in the API's canonical lead representation. Reuse existing equivalent fields where possible rather than duplicating the same information in new columns.

| Field | Meaning / expected representation |
|---|---|
| `lead_id` | Unique ID generated by the backend/database; clients must not choose an ID for a new lead. |
| `client` | Project/client such as `Lakhotia`, `Shree Heights`, or `Vrindavan Greens`; validate against existing agreed values/configuration. |
| `property_type` | `industrial`, `flats`, or `plots`, unless existing approved config defines compatible values. |
| `lead_type` | `company`, `buyer`, or `broker`. |
| `source` | Examples in the PDF: `radar`, `referral`, `broker`, `chat`, `ad`, `apollo`. Keep source extensible/configurable; do not reject legitimate future tools without a documented reason. |
| `evidence` | Evidence supporting the lead: signal/source URL, referral ID, source record ID, or ad campaign context. Store safely and do not represent unverified evidence as verified. |
| `name` | Contact name, when known. |
| `company` | Company/organization, when known. |
| `phone` | Phone number in the original/display form; use a separate normalized value for matching where appropriate. |
| `email` | Email address in the display/canonical form; compare using a normalized value. |
| `linkedin_url` | LinkedIn profile URL, when available; normalize for matching without destroying the display value. |
| `consent` | Whether the applicable permission to submit/share/process the lead has been recorded. Follow the current model's meaning and do not silently reinterpret it as permission for every outreach channel. |
| `opted_out` | Whether the person has opted out. An opt-out must not be overwritten by later imports. |
| `fit_score` | Numeric score out of 100 if calculated; allow null/unknown when not yet scored. Database storage must not invent a score. |
| `fit_reasons` | Reasons for the score. Preserve compatibility with the current schema; a JSON array is suitable only if it matches the current API contract or can be exposed compatibly. |
| `intent` | `hot`, `warm`, or `cold` if determined; otherwise unknown/null according to the existing schema. |
| `stage` | Workflow stage. The PDF gives `new → qualified → contacted → engaged → visit_booked`. Preserve valid existing states and transitions; do not break more detailed current states by blindly replacing them. |
| `owner` | Person/team responsible for the next action, where known. |
| `next_action` | Next action description. |
| `next_action_date` | Date/time for the next action using a consistent ISO-8601 representation; store timestamps consistently (prefer UTC internally). |
| `utm_source` | Source tracking parameter. |
| `utm_campaign` | Campaign tracking parameter. |

The backend may maintain additional operational fields where needed, such as `created_at`, `updated_at`, `created_by`, `updated_by`, normalized deduplication fields, or audit identifiers. Keep them additive and document them. Do not let extra fields cause the agreed shared fields to disappear from API responses.

### Data modelling rules

- Inspect existing SQLAlchemy models first. Prefer extending the existing lead/referral model and serializers over creating a separate disconnected `leads_v2` table.
- Keep one canonical lead record shared by the app, API, dashboard, and future team tools.
- Where the system already separates a referral submission from a lead, preserve that relationship and map it to the canonical `lead_id`. Do not collapse unrelated workflow-history records into the lead row if that would remove auditability.
- Use backend-generated stable IDs. Preserve existing IDs and foreign-key relationships during migrations.
- Apply input validation and sensible length/type limits. Use parameterized ORM queries, database constraints where appropriate, and transactions for multi-step writes.
- Treat optional or unavailable information as unknown, not as fabricated data. Do not require a phone/email/LinkedIn URL if a legitimate lead source may not have it; use the existing duplicate policy and validation rules.
- Keep source, client, lead type, and property type extensible in a way that does not require a database code rewrite for every new lead source or supported project. Do not overengineer a full configurable CRM in this task.

## 5. Two core API operations: save a lead and get leads

First check the existing endpoint behaviour. If it already supports these operations, strengthen/extend it instead of creating duplicate routes.

### Save a lead

- Reuse the existing canonical endpoint if present. If there is no suitable endpoint, use `POST /api/v1/leads` as the standard create operation and document it.
- Validate the incoming JSON with the existing Pydantic/schema conventions.
- Generate `lead_id` server-side.
- Save through the existing persistence/session layer inside a transaction.
- Apply deduplication before creating a second record.
- Preserve consent and opt-out guardrails.
- Return a documented, stable JSON response including the created `lead_id` and whether the request created a new lead or matched an existing duplicate, consistent with current error/response conventions.
- If a repeated request is retried, use existing idempotency support if available; do not create extra lead records due to retry behaviour.
- Do not silently merge two people's records or overwrite referral/source attribution. If a likely duplicate is found, return a safe result that an authorised user can review.

### Get/search leads

- Reuse the existing `GET /api/v1/leads` endpoint if present.
- Return records from the same canonical database used by lead creation and the dashboard.
- Support pagination and practical optional filters/search when consistent with the existing code (for example `query`, `client`, `property_type`, `source`, `intent`, `stage`, and `owner`). Search `name`, `company`, `email`, `phone`, `evidence`, and LinkedIn URL where authorised. Avoid loading the entire database into memory.
- Keep current authentication and response shape compatible. If the current endpoint has admin protection, preserve it.
- Ensure the caller sees the latest committed record after a successful save, subject to their access permissions.
- Do not turn this into an internet research agent. The current requirement is to search/filter the team's stored leads. External research is out of scope unless an existing feature already supports it.

### Duplicate matching details

1. Normalize the phone for comparison by extracting digits; if there are at least 10 digits, compare the last 10 digits as the PDF instructs. Do not make empty/missing phone values match each other.
2. If no phone match is found, normalize email by trimming surrounding whitespace and case-folding; do not make empty/missing email values match each other.
3. If neither match is found, normalize the LinkedIn URL conservatively (scheme/host case, query/fragment removal, trailing slash normalization as appropriate). Do not merge different profiles merely because their URLs look similar.
4. Keep original user-entered display values when appropriate; use normalised values for comparison.
5. Add tests for formatted phone variations, country-code variations, missing contact fields, email case differences, LinkedIn URL variations, and records that are not duplicates.
6. Follow existing privacy rules: a duplicate response must not disclose protected personal information to an unauthorised caller.
7. Keep initial referral ownership/source attribution intact; duplicate detection does not mean automatic reassignment.

## 6. Database strategy: local SQLite, shared hosted PostgreSQL

Use one persistence layer so application logic and API contracts work against both supported databases.

### Local development/demo

- Keep SQLite as the simple default for individual local development and offline tests if that is how the project currently runs.
- Preserve the current local database and provide a safe backup/export path before schema changes.
- Use SQLite-specific connection settings only for SQLite (for example, `check_same_thread=False` if needed by the existing FastAPI setup). Do not pass SQLite-only settings to PostgreSQL.

### Team use across different locations

- A single local SQLite file is not a remotely shared database. Do **not** ask teammates to sync a live database file through Drive/OneDrive/email/network storage, and do not expose the SQLite file directly over the internet.
- For the shared team environment, use a hosted PostgreSQL database reachable by the backend over a secured connection. Each team member should open the same deployed HTTPS application URL or call the protected API; they should **not** connect their local application to separate copies of the data.
- Keep the database private. The browser/frontend must never connect directly to PostgreSQL or receive `DATABASE_URL`/database credentials.
- Use the existing hosting provider if one is already configured. If a managed PostgreSQL service or production credential is not available, prepare/document the configuration but clearly report that remote sharing is not live yet. Do not pretend to provision cloud services without credentials and actual confirmation.

### Configuration and portability

- Use one environment variable for the database connection, preferably `DATABASE_URL`, with backwards compatibility for an existing DB variable if one already exists. Default to the current SQLite behaviour for local development.
- Select a PostgreSQL driver explicitly in dependencies if needed; ensure imports/settings work with both SQLite and PostgreSQL.
- Use the existing SQLAlchemy engine/session pattern. Separate database-specific engine options correctly. Ensure sessions close on success and exceptions and transactions roll back on failures.
- Add Alembic or use existing migrations if present. Make schema changes repeatable, versioned, and non-destructive. Do not rely only on startup `create_all()` as the long-term production migration strategy.
- A database migration must preserve lead IDs, referral attribution, visit records, audit history, consent/opt-out state, and foreign keys. If a reliable local SQLite-to-PostgreSQL migration is in scope, provide an explicit dry-run-capable script or a tested documented process that preserves IDs, reports row counts, and does not duplicate records. Never auto-upload local demo data to production without an explicit operator action.
- Add an example configuration with placeholders only. Never copy real secrets into tracked files.

## 7. Remote team sharing and security

The team shares the **application URL**, not the physical database file or the PostgreSQL admin credentials.

- The deployed app/API should use the single shared hosted `DATABASE_URL` server-side.
- Keep database networking restricted to the backend/approved hosting network where the provider supports it; use TLS for hosted database connections.
- Inspect current authentication. Preserve it and do not make lead read/write endpoints public. If the current dashboard cannot authenticate safely for a shared deployment, document that as a deployment blocker and propose the smallest compatible remedy rather than embedding a common admin key in frontend JavaScript.
- Ensure the deployed environment does not use a weak development default such as `demo-admin-key`. Fail safely or warn clearly if a weak/default secret is used outside development, following existing configuration conventions.
- Keep personal data out of routine logs. Log operational events without exposing phone/email unnecessarily.
- Check CORS/CSRF/origin protections only as relevant to the existing frontend architecture; do not broadly enable all origins with credentials.
- Add a `/health` or equivalent basic health check only if one does not already exist; it should not expose secrets, schema details, or personal records.
- Do not provide public database-admin access to all six teammates. Teammates should use the shared UI/API with appropriate authentication; direct DB access should be limited to maintainers who genuinely need it.

## 8. Preserve all existing workflows and integrations

This is a database integration task, not a rebuild of the whole platform. Preserve existing paths and workflows for:

- current dashboard/UI and its field names;
- `/api/v1/referrals`, `/api/v1/leads`, and other existing endpoint contracts;
- scoring and fit reasons;
- consent, contact consent, and opt-out gates;
- AI analysis and prepared Grok adapter/configuration;
- human approval records and follow-up drafts;
- site-visit state transitions;
- commission review gates;
- audit events and KPI endpoints;
- n8n HTTP Request/webhook integration and idempotency;
- existing test fixtures and demo instructions.

If one of these depends on a table/model that must change, add a compatible migration and regression test. Do not turn on real outreach or external actions as part of database work. Do not change scoring weights or invent business policies.

## 9. Required tests

Run all existing tests and add focused tests for the database/API layer. Include as many of these as fit the current architecture:

1. The current test suite still passes.
2. Save a valid synthetic lead; confirm a stable `lead_id` is returned.
3. Retrieve that lead through the existing get/list endpoint, proving it uses the same database.
4. Search/filter and pagination work without returning duplicate pages or loading every record.
5. Phone deduplication compares last 10 digits and catches formatting/country-code variants.
6. Email deduplication ignores surrounding whitespace and case.
7. LinkedIn deduplication normalizes safe URL variants.
8. Missing identifiers do not cause false duplicates.
9. Duplicate submission does not create another lead and does not overwrite original attribution or opt-out state.
10. Invalid enum/type/length values are rejected clearly.
11. Protected endpoints remain protected; unauthorised callers cannot read private records.
12. Database errors roll back cleanly and do not leave partial writes.
13. SQLAlchemy/session configuration works for the current SQLite test setup; add PostgreSQL compatibility tests where a test database is available. Do not claim live PostgreSQL verification without actually running it.
14. Schema migration upgrades without dropping existing records. Test with a copy/temporary database, not the user's real database.
15. Existing AI, consent, audit, site-visit, commission, and KPI behaviours still pass their prior regression tests.

Use synthetic test data. Never use real prospects' contact information in committed fixtures.

## 10. Documentation required

Update the README (or add a focused `docs/database.md`) with:

- current database architecture and the path data takes from UI/tool → API → validation/deduplication → database → read API/UI;
- exact shared lead fields and a synthetic JSON request example;
- the save/get endpoints, authentication requirement, example request/response, duplicate response behaviour, filters and pagination;
- how to run locally with SQLite;
- how to configure a hosted PostgreSQL `DATABASE_URL` safely;
- how other team members access the same data using the deployed application URL;
- what is and is not live, required deployment steps, and how to back up/restore/migrate without data loss;
- how to run the tests and migrations;
- how the Grok connection is configured today, without exposing a key.

Provide one synthetic example lead that can be used to confirm the integration. Keep its contact details fake and clearly marked as synthetic. The exact lead can be based on the PDF's demo flow (for example, `Softein Bharat`), but do not invent factual commercial claims or real contact details.

## 11. Implementation order

Follow this sequence to reduce risk:

**Phase A — Baseline and inventory**
- Inspect files/routes/models/config/tests.
- Run current tests and capture baseline.
- Summarize current data flow and risk areas.

**Phase B — Canonical model and compatible API**
- Extend the existing data model/API to use the shared field contract.
- Implement or preserve save/get/search operations.
- Implement exact duplicate precedence without erasing original attribution.
- Ensure dashboard and existing referral intake still work.

**Phase C — Portability and migrations**
- Add configurable SQLite/PostgreSQL connection support through the current SQLAlchemy layer.
- Add safe versioned migrations and configuration docs.
- Do not switch the running environment to PostgreSQL without a supplied URL and an explicit configuration step.

**Phase D — Security and validation**
- Verify authenticated read/write behaviour and secret handling.
- Run migrations on a temporary copy.
- Run regression tests and inspect changed files/diff.

**Phase E — Team handoff**
- Document how to deploy one shared instance and where teammates should visit.
- Provide one synthetic test lead and the exact API/UI validation steps.
- Clearly mark “local SQLite demo verified”, “PostgreSQL configuration prepared”, and “hosted shared database live” as separate statuses. Use only statuses that actual testing supports.

## 12. Definition of done

This task is complete only when:

- [ ] Antigravity first inspected the existing workspace and recorded the baseline test result.
- [ ] There is one canonical lead store, not a new disconnected database/table.
- [ ] Shared lead field names are available in a consistent request/response format.
- [ ] One teammate/tool can save a synthetic lead and an authorised teammate can retrieve it through the same app/API.
- [ ] Duplicate matching follows phone-last-10-digits → email → LinkedIn order.
- [ ] Existing routes, UI, AI adapter, consent gates, audit history, site visits, commission-review logic, n8n starter, and KPIs are not broken.
- [ ] SQLite remains usable for local demo/tests.
- [ ] PostgreSQL can be selected with environment configuration for hosted team use, or any remaining external setup blocker is clearly documented.
- [ ] No database file or credentials are publicly exposed and no secrets are committed.
- [ ] Existing and new tests pass, or any pre-existing/unverified failures are reported honestly.
- [ ] README/database documentation explains how a remote teammate accesses the one shared database through the application URL.

## Final response format

When finished, report:

1. **What was already there** before your edits.
2. **What you changed**, naming the files and purpose of each change.
3. **What you deliberately did not change** to protect other people's work.
4. **Test results**, with exact command and pass/fail count.
5. **Database status**: local SQLite, PostgreSQL compatibility, and hosted remote sharing—each marked separately as verified, prepared, or blocked.
6. **How Mayur should test** saving one synthetic lead and reading it back.
7. **What must still be configured manually** (for example, hosting, managed PostgreSQL, secrets, or deployment) before all teammates at different locations can access the same live data.

Do not claim success for any external service you could not actually access and verify.
