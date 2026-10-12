# Matrix360 · Central Lead Intelligence Platform

> **Mayur's Shared Database & Canonical API Foundation**  
> *Matrix360 · Intern Team Project · October 2026*

---

## 1. System Overview & Architecture

Matrix360 is a central lead intelligence system unifying six intern team responsibilities across three property developments:

1. **Lakhotia** — Industrial plots and manufacturing space (Initial Target).
2. **Shree Heights** — Residential 2 & 3 BHK flats in Hooghly (`WBRERA/P/HOO/2023/000504`).
3. **Vrindavan Greens** — Residential & commercial land plots.

### Architectural Core Principle: One Central Database
- **No teammate maintains an isolated database or spreadsheet.**
- **Never sync raw SQLite files over Google Drive, OneDrive, or network folders.**
- **Local development:** Runs out-of-the-box on local SQLite (`sqlite:///./referralops.db`).
- **Shared multi-location team use:** The backend connects to a hosted PostgreSQL instance (`DATABASE_URL=postgresql://...`). Teammates open the **single hosted application URL** or call the protected REST API over HTTPS.

---

## 2. Mayur's Database & API Foundation (What Has Been Built)

1. **Canonical Shared Schema:** 21 standardized fields shared across all tools:
   - `lead_id`, `client`, `property_type`, `lead_type`, `source`, `evidence`, `name`, `company`, `phone`, `email`, `linkedin_url`, `consent`, `opted_out`, `fit_score`, `fit_reasons`, `intent`, `stage`, `owner`, `next_action`, `next_action_date`, `utm_source`, `utm_campaign`.
2. **3-Step Deduplication Engine:**
   - **Step 1 — Phone (Trailing 10 Digits):** Extracts all digits; matches last 10 digits regardless of formatting or country codes (e.g. `+91 9876543210` matches `09876543210`).
   - **Step 2 — Email:** Whitespace-trimmed and case-folded.
   - **Step 3 — LinkedIn URL:** Normalized path without protocol, `www`, or tracking query parameters.
   - *Safety Guarantee:* Missing fields never match; duplicates preserve original attribution and flag records for review.
3. **Deterministic Scoring Engine (0–100):** Multi-property configurable JSON profiles (`industrial`, `flats`, `plots`) with automatic **Hot / Warm / Cold** intent classification.
4. **Shared Server-Side AI Connection:** Single managed Grok / xAI connection with deterministic local demo fallback (`AI_PROVIDER=demo | xai | openai`).
5. **Non-Destructive Database Migrations:** Alembic versioned migrations (`alembic/versions/b44e2fae97e3_add_canonical_lead_fields_and_dedup_keys.py`).
6. **Multi-Property Dashboard:** Interactive web interface with real-time search, filters, lead passport viewer, and one-click demo seeder.
7. **29 Automated Tests:** 100% green pytest test suite.

---

## 3. Team Integration Guide (How Teammates Connect)

All tools communicate with Mayur's central database via the standardized REST API.

```
                  ┌────────────────────────────────────────┐
                  │          Matrix360 Hosted URL          │
                  │        https://matrix360.live          │
                  └───────────────────┬────────────────────┘
                                      │
       ┌──────────────────────────────┼──────────────────────────────┐
       │                              │                              │
┌──────▼──────┐                ┌──────▼──────┐                ┌──────▼──────┐
│   Shalini   │                │   Avinash   │                │  Peeyusha   │
│Landing Page │                │Chat Widget  │                │Radar Scraper│
└──────┬──────┘                └──────┬──────┘                └──────┬──────┘
       │                              │                              │
       └──────────────────────┐       │       ┌──────────────────────┘
                              │       │       │
                        POST  ▼       ▼       ▼
                       /api/v1/leads (Mayur's Central API)
                                      │
                                      ▼
                       3-Step Deduplication Check
                       (Phone 10 → Email → LinkedIn)
                                      │
                                      ▼
                        Deterministic Scoring (Pratha)
                                      │
                                      ▼
                     One Central Database (SQLite / Postgres)
                                      │
       ┌──────────────────────────────┼──────────────────────────────┐
       │                              │                              │
┌──────▼──────┐                ┌──────▼──────┐                ┌──────▼──────┐
│   Tanmayi   │                │    Mayur    │                │    Team     │
│  WhatsApp   │                │ Central Web │                │ n8n Webhook │
│Consent Gate │                │  Dashboard  │                │ Reminders   │
└─────────────┘                └─────────────┘                └─────────────┘
```

### A. Shalini — Landing Page & Ad Inquiries (`Shree Heights`)
- **Her Role:** Landing page for Shree Heights with RERA registration `WBRERA/P/HOO/2023/000504`, 2/3 BHK options, and UTM tracking.
- **Hosted Page:** Available at [`/shree-heights`](http://127.0.0.1:8000/shree-heights).
- **How to Send Leads:**
  Form submissions send a `POST` request to `/api/v1/leads`:
  ```json
  {
    "client": "Shree Heights",
    "property_type": "flats",
    "lead_type": "buyer",
    "source": "ad",
    "evidence": "Shree Heights Meta Ad Click",
    "name": "Ananya Das",
    "company": "Individual Buyer",
    "phone": "+91 9830012345",
    "email": "ananya.das@example.test",
    "timeline": "immediate",
    "site_visit_interest": true,
    "consent": true,
    "utm_source": "meta_ads",
    "utm_campaign": "monsoon_launch"
  }
  ```

### B. Avinash — Website Chat Widget
- **Her/His Role:** Interactive chat widget qualifying prospects and booking site visits.
- **How to Send Leads:**
  When a visitor provides contact details in chat, send to `/api/v1/leads`:
  ```json
  {
    "client": "Lakhotia",
    "property_type": "industrial",
    "lead_type": "company",
    "source": "chat",
    "evidence": "Website chat qualification session #402",
    "name": "Vikram Malhotra",
    "company": "Malhotra Steels",
    "phone": "+91 9820011223",
    "email": "vikram@malhotrasteels.test",
    "plot_size_sqm": 2000,
    "budget_inr": 28000000,
    "timeline": "within_3_months",
    "site_visit_interest": true,
    "consent": true
  }
  ```

### C. Tanmayi — WhatsApp Follow-Up & Consent Gate
- **Her Role:** Outreach messaging with strict opt-out compliance.
- **How to Query Leads for Outreach:**
  Call `GET /api/v1/leads` with `X-Admin-Key`:
  - Filter for leads with `consent=true` and `opted_out=false`.
- **How to Record an Opt-out:**
  If a prospect replies `STOP` or requests no contact, call:
  `POST /api/v1/leads/{lead_id}/consent/withdraw-contact`
  ```json
  {
    "requested_by": "Tanmayi WhatsApp Bot",
    "source": "phone",
    "evidence_reference": "Prospect requested STOP in WhatsApp chat"
  }
  ```
  *The system immediately marks `opted_out=true`, permanently blocking future outreach.*

### D. Pratha — Qualification Scoring & Ranking
- **Her Role:** Transparent, deterministic scoring out of 100 with separate industry profiles.
- **How It Works:**
  - Configured in [`app/industry_profiles.json`](file:///c:/Users/MAYUR/Documents/CODEs/referralops_demo/app/industry_profiles.json).
  - Automatically executed on every lead submission.
  - Scores ≥ 75 are marked as `priority_review` and assigned `intent="hot"`.
  - Full scoring rationale is saved in `fit_reasons`.

### E. Peeyusha — Radar Signals & Apollo Leads
- **Her Role:** Signal scraper collecting industrial expansion and relocations.
- **How to Import Radar Signals:**
  Send signals to `/api/v1/leads` with `source="radar"`:
  ```json
  {
    "client": "Lakhotia",
    "property_type": "industrial",
    "lead_type": "company",
    "source": "radar",
    "evidence": "https://radar.signal.internal/signal/sotefin-bharat-expansion-2026",
    "company": "Sotefin Bharat",
    "name": "Demo Representative",
    "phone": "+91 9000000042",
    "email": "contact@sotefin-bharat.synthetic.test",
    "linkedin_url": "https://www.linkedin.com/company/sotefin-bharat-parking",
    "industry": "manufacturing",
    "plot_size_sqm": 2500,
    "budget_inr": 35000000,
    "timeline": "within_6_months",
    "is_decision_maker": true,
    "site_visit_interest": true,
    "consent": true,
    "business_requirements": "Automated car parking systems manufacturer expanding operations."
  }
  ```

---

## 4. How to Run Locally

### Prerequisites
- Python 3.11+ (Python 3.14 compatible)
- Windows PowerShell, macOS, or Linux terminal

### 1. Setup Virtual Environment
```powershell
# Clone or navigate into the directory
cd referralops_demo

# Create virtual environment
py -m venv .venv

# Activate environment (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# (On Linux / macOS use: source .venv/bin/activate)

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment
```powershell
Copy-Item .env.example .env
```
Default `.env` configuration runs offline in SQLite mode with demo AI:
```ini
DATABASE_URL=sqlite:///./referralops.db
ADMIN_API_KEY=demo-admin-key
AI_PROVIDER=demo
```

### 3. Run Database Migrations
```powershell
alembic upgrade head
```

### 4. Start the Application
```powershell
uvicorn app.main:app --reload
```

### 5. Access the Platform
- **Central Web Dashboard:** [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
- **Shree Heights Landing Page:** [http://127.0.0.1:8000/shree-heights](http://127.0.0.1:8000/shree-heights)
- **Interactive Swagger API Docs:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health Check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 5. Multi-Location Shared Deployment (PostgreSQL)

To share **one central database** with teammates in different locations:

1. **Provision a Managed PostgreSQL Database:**
   - Free/low-cost providers: Supabase, Neon, Railway, Render Postgres, or AWS RDS.
2. **Set the Hosted Database URL in `.env`:**
   ```ini
   DATABASE_URL=postgresql://user:password@db.example.host:5432/matrix360?sslmode=require
   ADMIN_API_KEY=your_secure_random_admin_key
   ```
3. **Run Migrations on the PostgreSQL Instance:**
   ```powershell
   alembic upgrade head
   ```
4. **Deploy the App to Cloud Hosting:**
   - Host the FastAPI app on Render, Fly.io, Railway, or AWS.
   - Set the environment variables in your hosting provider's dashboard.
5. **Share the Application URL:**
   - Share `https://matrix360-leads.onrender.com` with teammates.
   - **Never share the PostgreSQL connection string or credentials directly with other tools.**

---

## 6. Shared Grok / xAI Connection

The platform includes a single server-side Grok / xAI connection so individual teammates do not need separate API keys:

```ini
AI_PROVIDER=xai
XAI_API_KEY=your_xai_grok_key_here
XAI_MODEL=grok-beta
XAI_TIMEOUT_SECONDS=15
```
- When `AI_PROVIDER=demo`, all analysis and follow-up drafts run locally and deterministically.
- Grok analysis runs securely on the backend; keys are never exposed in browser JavaScript.

---

## 7. Running the Automated Tests

Run the complete test suite:
```powershell
pytest -v
```

**Results (29 passed):**
- 19 baseline tests in `tests/test_api.py` (Referral intake, AI providers, human approval gates, audit events, KPIs).
- 10 integration tests in `tests/test_matrix360_database.py` (Canonical save/retrieve, phone-10/email/LinkedIn deduplication, search/filter, idempotency, Shree Heights landing page, Sotefin Bharat demo lead, demo seeding).

---

## 8. Complete API Map

| Method | Endpoint | Description | Auth |
|---|---|---|---|
| `POST` | `/api/v1/leads` | **Save a Lead** (Canonical endpoint with 3-step dedup & scoring) | Public / Partner |
| `GET` | `/api/v1/leads` | **List & Search Leads** (Filters by client, property, intent, source, `q`) | `X-Admin-Key` |
| `GET` | `/api/v1/leads/{id}` | **Lead Passport** (Full record, audit trail, duplicate claims) | `X-Admin-Key` |
| `POST` | `/api/v1/leads/{id}/approval` | Approve/hold/reject AI follow-up draft | `X-Admin-Key` |
| `POST` | `/api/v1/leads/{id}/reanalyze` | Re-run AI analysis | `X-Admin-Key` |
| `POST` | `/api/v1/leads/{id}/consent/withdraw-contact` | **Record Opt-out** (Tanmayi's compliance gate) | `X-Admin-Key` |
| `POST` | `/api/v1/leads/{id}/site-visits` | Request on-site visit | `X-Admin-Key` |
| `PATCH` | `/api/v1/site-visits/{id}` | Schedule / complete / cancel site visit | `X-Admin-Key` |
| `POST` | `/api/v1/demo/seed` | **Seed Synthetic Demo Leads** (Sotefin Bharat, Shree Heights, Vrindavan) | Public |
| `GET` | `/shree-heights` | **Shalini's Shree Heights Landing Page** | Public |
| `GET` | `/health` | Service health status | Public |
| `GET` | `/api/v1/kpis` | Operational KPIs & conversion rates | `X-Admin-Key` |

---

## 9. Synthetic Demo Lead (`Sotefin Bharat`)

To verify the end-to-end integration with the demo lead from the Matrix360 build plan:

**Using PowerShell:**
```powershell
$body = @{
    client = "Lakhotia"
    property_type = "industrial"
    lead_type = "company"
    source = "radar"
    evidence = "https://radar.signal.internal/signal/sotefin-bharat-expansion-2026"
    name = "Demo Representative"
    company = "Sotefin Bharat"
    phone = "+91 9000000042"
    email = "contact@sotefin-bharat.synthetic.test"
    linkedin_url = "https://www.linkedin.com/company/sotefin-bharat-parking"
    consent = $true
    industry = "manufacturing"
    plot_size_sqm = 2500
    budget_inr = 35000000
    timeline = "within_6_months"
    is_decision_maker = $true
    site_visit_interest = $true
    business_requirements = "Automated car parking systems manufacturer expanding operations."
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/leads" -Method Post -ContentType "application/json" -Body $body
```

**Retrieve it:**
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/leads?q=Sotefin" -Headers @{"X-Admin-Key"="demo-admin-key"}
```
