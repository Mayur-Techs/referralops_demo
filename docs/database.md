# Matrix360 — Mayur's Shared Lead Database & Canonical API

**Status:**
- **Local SQLite Demo:** Verified & operational
- **PostgreSQL Configuration:** Prepared and tested in SQLAlchemy models & Alembic migrations
- **Shared Hosted Database:** Ready to deploy via hosted application URL

This guide defines how all team tools (Avinash's chat widget, Shalini's landing page, Tanmayi's consent/WhatsApp gate, Pratha's qualification scoring, and Abhinav/Peeyusha's Radar signal intake) read and write to **one central database** via Mayur's shared API.

---

## 1. Architectural Principle: One Database, One API

1. **No team member maintains an isolated competing database.**
2. **Never sync raw SQLite files over Google Drive, OneDrive, or a network share.** SQLite is designed for local single-process access; multi-user network sharing causes locks and corruption.
3. For local development on one laptop: **SQLite** (`sqlite:///./referralops.db`).
4. For remote team use across different locations: deploy this application to a hosted URL (Render, Fly.io, Railway, AWS, etc.) with a **managed PostgreSQL database** (`DATABASE_URL=postgresql://...`). Teammates connect to the **hosted application URL**, not directly to the raw database port.

---

## 2. Canonical Shared Lead Format

Every form, script, or n8n workflow sends and receives these exact snake_case fields:

| Field | Type | Description |
|---|---|---|
| `lead_id` | String (UUID) | Stable unique ID generated server-side. |
| `client` | String | Project client: `Lakhotia`, `Shree Heights`, or `Vrindavan Greens`. |
| `property_type` | String | Controlled: `industrial`, `flats`, or `plots`. |
| `lead_type` | String | Controlled: `company`, `buyer`, or `broker`. |
| `source` | String | Origin: `radar`, `referral`, `broker`, `chat`, `ad`, `apollo`, `landing_page`. |
| `evidence` | String | Source URL, referral ID, ad context, or signal evidence link. |
| `name` | String | Contact person name. |
| `company` | String | Prospect company or organization name. |
| `phone` | String | Display phone number (normalized server-side for matching). |
| `email` | String | Display email address (lowercased server-side for matching). |
| `linkedin_url` | String (optional) | Canonical LinkedIn profile URL. |
| `consent` | Boolean | Whether contact permission has been recorded. |
| `opted_out` | Boolean | Global opt-out flag (overrides all outreach immediately). |
| `fit_score` | Integer (0–100) | Deterministic qualification score. |
| `fit_reasons` | List[String] | Explanation of score and missing requirements. |
| `intent` | String | Coordinated intent rule: `hot`, `warm`, or `cold`. |
| `stage` | String | Lifecycle stage: `new` → `qualified` → `contacted` → `engaged` → `visit_booked`. |
| `owner` | String (optional) | Assigned team member handling the prospect. |
| `next_action` | String (optional) | Specific next operational step. |
| `next_action_date` | String (ISO-8601) | Target completion timestamp (UTC). |
| `utm_source` | String (optional) | Marketing attribution source parameter. |
| `utm_campaign` | String (optional) | Marketing attribution campaign parameter. |

---

## 3. Two Core Endpoints

### A. Save a Lead: `POST /api/v1/leads`

Saves a lead into the central database. Enforces 3-step deduplication, calculates deterministic qualification score, assigns Hot/Warm/Cold intent, and records audit trail.

**Headers:**
- `Content-Type: application/json`
- `Idempotency-Key: <unique-uuid>` *(optional, recommended for webhooks & retries)*

**Request Example:**
```json
{
  "client": "Lakhotia",
  "property_type": "industrial",
  "lead_type": "company",
  "source": "radar",
  "evidence": "https://radar.signal.internal/signal/sotefin-bharat-expansion-2026",
  "name": "Synthetic Representative",
  "company": "Sotefin Bharat",
  "phone": "+91 9000000042",
  "email": "contact@sotefin-bharat.synthetic.test",
  "linkedin_url": "https://www.linkedin.com/company/sotefin-bharat-parking",
  "consent": true,
  "industry": "manufacturing",
  "plot_size_sqm": 2500,
  "budget_inr": 35000000,
  "timeline": "within_6_months",
  "is_decision_maker": true,
  "site_visit_interest": true,
  "business_requirements": "Automated car parking systems manufacturer expanding operations."
}
```

**Success Response (`201 Created`):**
```json
{
  "lead_id": "3b29c512-88f2-4e4b-97e3-0d3128919012",
  "is_duplicate": false,
  "message": "Lead saved successfully in central database.",
  "lead": {
    "lead_id": "3b29c512-88f2-4e4b-97e3-0d3128919012",
    "client": "Lakhotia",
    "property_type": "industrial",
    "company": "Sotefin Bharat",
    "name": "Synthetic Representative",
    "phone": "+919000000042",
    "email": "contact@sotefin-bharat.synthetic.test",
    "fit_score": 83,
    "intent": "hot",
    "stage": "new",
    "consent": true,
    "opted_out": false
  }
}
```

**Duplicate Match Response (`201 Created` with duplicate review flag):**
```json
{
  "lead_id": "3b29c512-88f2-4e4b-97e3-0d3128919012",
  "is_duplicate": true,
  "duplicate_match_reason": "matched_phone_last_10",
  "message": "Existing lead matched by matched_phone_last_10. Original attribution preserved.",
  "lead": { ... }
}
```

---

### B. Get & Search Leads: `GET /api/v1/leads`

Searches and retrieves committed leads from the single central database.

**Headers:**
- `X-Admin-Key: demo-admin-key` *(or configured `ADMIN_API_KEY`)*

**Optional Query Filters:**
- `q`: Search keyword across name, company, email, phone, evidence, LinkedIn URL.
- `client`: Filter by `Lakhotia`, `Shree Heights`, or `Vrindavan Greens`.
- `property_type`: Filter by `industrial`, `flats`, or `plots`.
- `source`: Filter by `radar`, `chat`, `ad`, `referral`, etc.
- `intent`: Filter by `hot`, `warm`, or `cold`.
- `stage`: Filter by `new`, `qualified`, `contacted`, `engaged`, `visit_booked`.
- `owner`: Filter by assignee name.
- `limit`: Number of records (default 100, max 500).
- `offset`: Pagination offset (default 0).

**Example Request:**
```bash
curl -H "X-Admin-Key: demo-admin-key" "http://127.0.0.1:8000/api/v1/leads?client=Shree+Heights&property_type=flats"
```

---

## 4. 3-Step Deduplication Rule

When a lead is submitted, the system checks for existing records in this **exact priority order**:

1. **Normalized Phone (Last 10 Digits):** Extracts all digits from the phone number. If 10 or more digits exist, compares the trailing 10 digits (`dedup_phone`). Catches `+91 9876543210`, `09876543210`, and `9876543210`.
2. **Normalized Email:** Trims surrounding whitespace and lowercases the address (`dedup_email`). Catches `User@Example.Test ` and `user@example.test`.
3. **Normalized LinkedIn URL:** Strips protocol (`http`/`https`), `www`, tracking query parameters, and trailing slashes (`dedup_linkedin`).

**Deduplication Safety Guarantees:**
- Missing/empty fields **never** match each other.
- Matching records are **never silently merged or overwritten**.
- Original source and referral partner attribution is preserved.
- A duplicate submission event is recorded in `referral_submissions` and flagged for human review.

---

## 5. Local SQLite vs Hosted PostgreSQL

### A. Local Run (SQLite)
```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```
Database runs locally at `referralops.db`.

### B. Hosted Remote Run (PostgreSQL)
1. Provision a managed PostgreSQL instance (e.g. Supabase, Neon, AWS RDS, Render Postgres).
2. Set `DATABASE_URL` in environment variables:
   ```env
   DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
   ```
3. Run Alembic schema migrations:
   ```powershell
   alembic upgrade head
   ```
4. Start the application with a production ASGI server (e.g. `uvicorn app.main:app --host 0.0.0.0 --port 8000`).
5. Share the HTTPS app URL (e.g. `https://matrix360-leads.onrender.com`) with teammates.

---

## 6. Shared AI / Grok Configuration

Server-side configuration only — API keys are never exposed in browser JavaScript or logs:
```env
AI_PROVIDER=xai
XAI_API_KEY=xai-your-api-key-here
XAI_MODEL=grok-beta
XAI_TIMEOUT_SECONDS=15
```
In `demo` mode (`AI_PROVIDER=demo`), the system runs deterministically without an external key.

---

## 7. How Mayur Verifies the Integration

1. Start server: `uvicorn app.main:app`
2. Run test suite: `pytest -v` (27 passing tests)
3. Submit synthetic Sotefin Bharat lead via `POST /api/v1/leads`:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/leads" -Method Post -ContentType "application/json" -Body '{"client":"Lakhotia","property_type":"industrial","lead_type":"company","source":"radar","evidence":"https://radar.internal/signal/sotefin","name":"Demo Rep","company":"Sotefin Bharat","phone":"+91 9000000042","email":"contact@sotefin-bharat.synthetic.test","consent":true}'
   ```
4. Retrieve the lead via `GET /api/v1/leads`:
   ```powershell
   Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/leads" -Headers @{"X-Admin-Key"="demo-admin-key"}
   ```
