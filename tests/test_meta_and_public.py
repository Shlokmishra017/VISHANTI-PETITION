from app.auth import create_access_token

def test_meta_categories_endpoint(client, fixtures):
    resp = client.get("/api/meta/categories")
    assert resp.status_code == 200
    categories = resp.json()
    assert len(categories) >= 1
    assert any(c["name"] == "Exam Grading" for c in categories)

def test_public_verify_and_metrics(client, fixtures):
    # test public overall verification status
    verify_resp = client.get("/api/public/verify")
    assert verify_resp.status_code == 200
    data = verify_resp.json()
    assert data["tamper_evident_status"] == "VALID"
    assert data["all_valid"] is True
    assert data["total_cases_verified"] >= 1

    # test public metrics
    metrics_resp = client.get("/api/public/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert "total_cases" in metrics
    assert "departments" in metrics

def test_dev_tick_and_tamper(client, fixtures):
    case = fixtures["case"]

    # trigger dev tick
    tick_resp = client.post("/api/dev/tick")
    assert tick_resp.status_code == 200
    assert "escalated_cases" in tick_resp.json()

    # trigger dev tamper on genesis event
    tamper_resp = client.post(
        "/api/dev/tamper",
        json={"case_ref_or_id": case.id, "target_seq": 1, "modified_text": "UNAUTHORIZED_EDIT"}
    )
    assert tamper_resp.status_code == 200
    assert tamper_resp.json()["status"] == "tampered"

    # public verify must now detect compromise
    verify_resp = client.get("/api/public/verify")
    assert verify_resp.json()["all_valid"] is False
    assert verify_resp.json()["tamper_evident_status"] == "COMPROMISED"

