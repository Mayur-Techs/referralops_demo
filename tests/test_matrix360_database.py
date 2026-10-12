"""Focused test suite for Mayur's Matrix360 shared lead database and API layer.

Verifies:
1. Canonical lead creation via POST /api/v1/leads
2. Retrieval via GET /api/v1/leads and GET /api/v1/leads/{lead_id}
3. 3-step deduplication in exact order: Phone (last 10 digits) -> Email -> LinkedIn URL
4. Formatted phone, email casing, and LinkedIn variations
5. Missing identifier safety (no false duplicate matches)
6. Original attribution preservation on duplicate claim
7. Search/filter by client, property_type, source, query term, and pagination
8. Idempotency key replay and conflict protection
9. Synthetic Sotefin Bharat lead from Matrix360 build plan
"""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ADMIN = {"X-Admin-Key": "test-secret"}


@pytest.fixture
def test_client(tmp_path):
    db_file = tmp_path / "matrix360_test.db"
    settings = Settings(
        database_url=f"sqlite:///{db_file.as_posix()}",
        admin_api_key="test-secret",
        ai_provider="demo",
        consent_notice_version="matrix360-v1",
    )
    application = create_app(settings=settings)
    return TestClient(application)


def test_save_and_retrieve_canonical_lead(test_client):
    payload = {
        "client": "Shree Heights",
        "property_type": "flats",
        "lead_type": "buyer",
        "source": "chat",
        "evidence": "Website chat enquiry for 3 BHK flat",
        "name": "Priya Sharma",
        "company": "Tech Solutions India",
        "phone": "+91 9820011223",
        "email": "priya.sharma@example.test",
        "linkedin_url": "https://www.linkedin.com/in/priya-sharma-tech",
        "consent": True,
        "opted_out": False,
        "owner": "Avinash",
        "next_action": "Schedule video call",
        "utm_source": "google_ads",
        "utm_campaign": "monsoon_launch",
    }
    # Save lead
    res = test_client.post("/api/v1/leads", json=payload)
    assert res.status_code == 201
    body = res.json()
    assert body["is_duplicate"] is False
    assert "lead_id" in body
    lead_id = body["lead_id"]

    saved_lead = body["lead"]
    assert saved_lead["lead_id"] == lead_id
    assert saved_lead["client"] == "Shree Heights"
    assert saved_lead["property_type"] == "flats"
    assert saved_lead["source"] == "chat"
    assert saved_lead["name"] == "Priya Sharma"
    assert saved_lead["company"] == "Tech Solutions India"
    assert saved_lead["email"] == "priya.sharma@example.test"
    assert saved_lead["phone"] == "+919820011223"
    assert saved_lead["consent"] is True
    assert saved_lead["opted_out"] is False

    # Retrieve through GET /api/v1/leads
    get_res = test_client.get("/api/v1/leads", headers=ADMIN)
    assert get_res.status_code == 200
    leads = get_res.json()
    assert len(leads) == 1
    assert leads[0]["lead_id"] == lead_id
    assert leads[0]["client"] == "Shree Heights"

    # Retrieve through GET /api/v1/leads/{lead_id}
    detail_res = test_client.get(f"/api/v1/leads/{lead_id}", headers=ADMIN)
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["lead_id"] == lead_id
    assert detail["name"] == "Priya Sharma"
    assert "audit_history" in detail
    assert "referral_history" in detail


def test_phone_deduplication_matches_last_10_digits(test_client):
    # First lead
    p1 = {
        "client": "Lakhotia",
        "name": "Rajesh Kumar",
        "company": "Kumar Logistics",
        "phone": "+91 9876543210",
        "email": "rajesh@kumarlogistics.test",
        "consent": True,
    }
    r1 = test_client.post("/api/v1/leads", json=p1)
    assert r1.status_code == 201
    lead_id = r1.json()["lead_id"]

    # Second lead with country code variations: 09876543210 (same last 10 digits)
    p2 = {
        "client": "Lakhotia",
        "name": "Rajesh K.",
        "company": "Kumar Transport",
        "phone": "09876543210",  # different formatting, same last 10 digits
        "email": "different_email@example.test",
        "consent": True,
    }
    r2 = test_client.post("/api/v1/leads", json=p2)
    assert r2.status_code == 201
    b2 = r2.json()
    assert b2["is_duplicate"] is True
    assert b2["lead_id"] == lead_id
    assert b2["duplicate_match_reason"] == "matched_phone_last_10"
    # Ensure original lead attribution was preserved
    assert b2["lead"]["email"] == "rajesh@kumarlogistics.test"


def test_email_deduplication_ignores_case_and_whitespace(test_client):
    # First lead
    p1 = {
        "client": "Vrindavan Greens",
        "name": "Ananya Sen",
        "company": "Sen Enterprises",
        "phone": "+91 9111122222",
        "email": "ananya.sen@example.test",
        "consent": True,
    }
    r1 = test_client.post("/api/v1/leads", json=p1)
    assert r1.status_code == 201
    lead_id = r1.json()["lead_id"]

    # Second lead with different phone, but same email with mixed case & spaces
    p2 = {
        "client": "Vrindavan Greens",
        "name": "Ananya Sen",
        "company": "Sen Capital",
        "phone": "+91 9999988888",
        "email": "  AnAnYa.SeN@ExAmPlE.tEsT  ",
        "consent": True,
    }
    r2 = test_client.post("/api/v1/leads", json=p2)
    assert r2.status_code == 201
    b2 = r2.json()
    assert b2["is_duplicate"] is True
    assert b2["lead_id"] == lead_id
    assert b2["duplicate_match_reason"] == "matched_email"


def test_linkedin_deduplication_matches_profile_key(test_client):
    # First lead with unique phone and unique email
    p1 = {
        "client": "Lakhotia",
        "name": "Vikram Malhotra",
        "company": "Malhotra Steels",
        "phone": "+91 9000100001",
        "email": "vikram1@example.test",
        "linkedin_url": "https://www.linkedin.com/in/vikram-malhotra-steel/",
        "consent": True,
    }
    r1 = test_client.post("/api/v1/leads", json=p1)
    assert r1.status_code == 201
    lead_id = r1.json()["lead_id"]

    # Second lead: different phone, different email, same LinkedIn with query param and http
    p2 = {
        "client": "Lakhotia",
        "name": "Vikram M",
        "company": "VM Industries",
        "phone": "+91 9000200002",
        "email": "vikram2@example.test",
        "linkedin_url": "http://linkedin.com/in/vikram-malhotra-steel?trackingId=xyz",
        "consent": True,
    }
    r2 = test_client.post("/api/v1/leads", json=p2)
    assert r2.status_code == 201
    b2 = r2.json()
    assert b2["is_duplicate"] is True
    assert b2["lead_id"] == lead_id
    assert b2["duplicate_match_reason"] == "matched_linkedin"


def test_missing_identifiers_do_not_cause_false_duplicates(test_client):
    # Lead A: has phone and email, no linkedin
    p1 = {
        "client": "Shree Heights",
        "name": "Buyer One",
        "company": "Firm A",
        "phone": "+91 9123456780",
        "email": "buyer1@example.test",
        "consent": True,
    }
    r1 = test_client.post("/api/v1/leads", json=p1)
    assert r1.status_code == 201

    # Lead B: completely different phone and email, also no linkedin
    p2 = {
        "client": "Shree Heights",
        "name": "Buyer Two",
        "company": "Firm B",
        "phone": "+91 9876543219",
        "email": "buyer2@example.test",
        "consent": True,
    }
    r2 = test_client.post("/api/v1/leads", json=p2)
    assert r2.status_code == 201
    assert r2.json()["is_duplicate"] is False
    assert r2.json()["lead_id"] != r1.json()["lead_id"]


def test_search_filter_and_pagination(test_client):
    # Create leads for different clients and sources
    test_client.post("/api/v1/leads", json={
        "client": "Shree Heights", "property_type": "flats", "source": "ad",
        "name": "Amit Shah", "company": "Gujarat Plastics", "phone": "+91 9011111111",
        "email": "amit@plastic.test", "consent": True,
    })
    test_client.post("/api/v1/leads", json={
        "client": "Lakhotia", "property_type": "industrial", "source": "radar",
        "name": "Suresh Patel", "company": "Patel Heavy Engineering", "phone": "+91 9022222222",
        "email": "suresh@patel.test", "consent": True,
    })
    test_client.post("/api/v1/leads", json={
        "client": "Shree Heights", "property_type": "flats", "source": "chat",
        "name": "Neha Gupta", "company": "Gupta Textiles", "phone": "+91 9033333333",
        "email": "neha@textile.test", "consent": True,
    })

    # Filter by client
    r_client = test_client.get("/api/v1/leads?client=Shree+Heights", headers=ADMIN)
    assert r_client.status_code == 200
    assert len(r_client.json()) == 2

    # Filter by source
    r_source = test_client.get("/api/v1/leads?source=radar", headers=ADMIN)
    assert r_source.status_code == 200
    assert len(r_source.json()) == 1
    assert r_source.json()[0]["company"] == "Patel Heavy Engineering"

    # Search query
    r_search = test_client.get("/api/v1/leads?q=Plastics", headers=ADMIN)
    assert r_search.status_code == 200
    assert len(r_search.json()) == 1
    assert r_search.json()[0]["name"] == "Amit Shah"

    # Pagination: limit 1, offset 1
    r_page = test_client.get("/api/v1/leads?limit=1&offset=1", headers=ADMIN)
    assert r_page.status_code == 200
    assert len(r_page.json()) == 1


def test_idempotency_key_prevents_duplicate_submission(test_client):
    key = "idem-key-test-12345"
    payload = {
        "client": "Lakhotia",
        "name": "Same Person",
        "company": "Same Company",
        "phone": "+91 9777788888",
        "email": "same@example.test",
        "consent": True,
    }

    # First request
    r1 = test_client.post("/api/v1/leads", json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code == 201
    lead_id = r1.json()["lead_id"]

    # Second request with same idempotency key and same payload -> returns replay
    r2 = test_client.post("/api/v1/leads", json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 201
    assert r2.json()["lead_id"] == lead_id
    assert r2.json().get("idempotent_replay") is True

    # Replay with same key but altered payload -> 409 Conflict
    altered = dict(payload, company="Altered Company Name")
    r3 = test_client.post("/api/v1/leads", json=altered, headers={"Idempotency-Key": key})
    assert r3.status_code == 409


def test_demo_lead_sotefin_bharat_synthetic(test_client):
    """Verifies Mayur's shared database can store Peeyusha's initial demo lead: Sotefin Bharat."""
    demo_lead = {
        "client": "Lakhotia",
        "property_type": "industrial",
        "lead_type": "company",
        "source": "radar",
        "evidence": "https://radar.signal.internal/signal/sotefin-bharat-expansion-2026",
        "name": "Demo Representative",
        "company": "Sotefin Bharat",
        "phone": "+91 9000000042",
        "email": "contact@sotefin-bharat.synthetic.test",
        "linkedin_url": "https://www.linkedin.com/company/sotefin-bharat-parking",
        "consent": True,
        "opted_out": False,
        "industry": "manufacturing",
        "plot_size_sqm": 2500,
        "budget_inr": 35000000,
        "timeline": "within_6_months",
        "is_decision_maker": True,
        "site_visit_interest": True,
        "business_requirements": "Automated car parking systems manufacturer expanding operations; requires industrial shed with high power load.",
    }
    res = test_client.post("/api/v1/leads", json=demo_lead)
    assert res.status_code == 201
    body = res.json()
    assert body["is_duplicate"] is False
    assert body["lead"]["company"] == "Sotefin Bharat"
    assert body["lead"]["source"] == "radar"
    assert body["lead"]["fit_score"] >= 75
    assert body["lead"]["intent"] == "hot"

    # Query by company name
    search_res = test_client.get("/api/v1/leads?q=Sotefin", headers=ADMIN)
    assert search_res.status_code == 200
    results = search_res.json()
    assert len(results) == 1
    assert results[0]["company"] == "Sotefin Bharat"


def test_shree_heights_landing_page_route(test_client):
    """Verifies Shalini's Shree Heights landing page is served correctly."""
    res = test_client.get("/shree-heights")
    assert res.status_code == 200
    assert "Shree Heights" in res.text
    assert "WBRERA/P/HOO/2023/000504" in res.text
    assert "Book a Site Visit" in res.text


def test_seed_demo_leads_endpoint(test_client):
    """Verifies POST /api/v1/demo/seed populates synthetic demo leads without duplicates."""
    seed_res = test_client.post("/api/v1/demo/seed")
    assert seed_res.status_code == 200
    body = seed_res.json()
    assert body["status"] == "ok"
    assert body["seeded_leads_count"] == 3

    # Calling seed a second time should be idempotent (0 newly created)
    seed_res2 = test_client.post("/api/v1/demo/seed")
    assert seed_res2.status_code == 200
    assert seed_res2.json()["seeded_leads_count"] == 0

    # Query leads
    leads = test_client.get("/api/v1/leads", headers=ADMIN).json()
    companies = {l["company"] for l in leads}
    assert "Sotefin Bharat" in companies
    assert "Individual Buyer" in companies
    assert "Kailash Agro Industries" in companies
