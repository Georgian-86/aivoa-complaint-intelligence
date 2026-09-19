"""HTTP contract."""


def test_health_reports_degraded_mode(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok"
    assert body["ai"]["mode"] == "deterministic-fallback"  # no key in tests
    assert body["database"]["status"] == "up"


def test_taxonomy_is_a_closed_vocabulary(client):
    body = client.get("/api/v1/complaints/taxonomy").json()
    assert "Critical" in body["severities"]
    assert body["severity_tat_days"]["Critical"] == 3
    assert len(body["complaint_types"]) > 10


def test_register_seeded_and_filterable(client):
    total = client.get("/api/v1/complaints").json()["total"]
    assert total >= 8

    critical = client.get("/api/v1/complaints", params={"severity": "Critical"}).json()
    assert critical["total"] >= 1
    assert all(item["severity"] == "Critical" for item in critical["items"])

    search = client.get("/api/v1/complaints", params={"q": "Ceftrioxam"}).json()
    assert search["total"] >= 1


def test_intake_text_populates_the_form(client, particulate_email):
    body = client.post(
        "/api/v1/intake/text", json={"text": particulate_email, "channel": "email"}
    ).json()
    assert body["form"]["batch_number"] == "CFX24B902"
    assert body["risk"]["severity"] == "Critical"
    assert body["completeness_score"] > 50
    assert len(body["trace"]) == 7
    assert body["fields"]["batch_number"]["evidence"]  # provenance is mandatory


def test_intake_rejects_empty_text(client):
    assert client.post("/api/v1/intake/text", json={"text": "hi"}).status_code == 422


def test_duplicate_detection_finds_the_seeded_pair(client):
    body = client.post("/api/v1/intake/text", json={
        "text": (
            "Complaint from Meridian Pharma Distribution. Black particulate matter was "
            "observed in the reconstituted solution. Product: Ceftrioxam 1 g Injection. "
            "Batch No.: CFX23A417. Quantity affected: 6 vials."
        ),
        "channel": "email",
    }).json()
    assert body["duplicates"]
    assert body["duplicates"][0]["score"] > 0.7


def test_create_read_and_transition_a_complaint(client):
    created = client.post("/api/v1/complaints", json={
        "product_name": "Test Product 10 mg",
        "batch_number": "TST0001",
        "complaint_type": "Packaging Defect",
        "description": "Blister pocket empty on opening.",
        "severity": "Minor",
        "complaint_source": "Customer Email",
        "customer_name": "Test Customer",
    }).json()
    assert created["reference"].startswith("CMP-")

    detail = client.get(f"/api/v1/complaints/{created['id']}").json()
    assert detail["audit_events"][0]["action"] == "created"

    moved = client.post(
        f"/api/v1/complaints/{created['id']}/status",
        json={"status": "Under Investigation", "note": "Batch record pulled."},
    ).json()
    assert moved["status"] == "Under Investigation"
    actions = [event["action"] for event in moved["audit_events"]]
    assert "status_changed" in actions


def test_unknown_status_is_rejected(client):
    created = client.post("/api/v1/complaints", json={
        "product_name": "Test Product B", "batch_number": "TST0002",
        "description": "x" * 40,
    }).json()
    response = client.post(
        f"/api/v1/complaints/{created['id']}/status", json={"status": "Teleported"}
    )
    assert response.status_code == 422


def test_copilot_answers_without_a_model(client):
    body = client.post("/api/v1/copilot", json={
        "thread_id": "t-1", "message": "What is still missing from this record?",
        "form": {"product_name": "Ceftrioxam 1 g Injection"},
    }).json()
    assert body["engine"] == "heuristic"
    assert "batch_number" in body["reply"] or "batch" in body["reply"].lower()


def test_analytics_shape(client):
    body = client.get("/api/v1/analytics/overview").json()
    assert body["total"] >= 8
    assert set(body["by_severity"]) >= {"Critical", "Major", "Minor"}
    assert isinstance(body["recurrence"], list)
