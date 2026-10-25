import io
from app.auth import create_access_token

def test_create_case_authenticated_with_attachment(client, fixtures):
    official = fixtures["official"]
    cat = fixtures["category"]
    token = create_access_token(data={"sub": official.id, "role": official.role})
    client.cookies.set("access_token", token)

    # create dummy pdf file in memory
    file_bytes = b"%PDF-1.4 dummy pdf content for testing attachment upload"
    files = [
        ("files", ("test_doc.pdf", io.BytesIO(file_bytes), "application/pdf"))
    ]
    data = {
        "title": "Broken laboratory spectrometer",
        "description": "Equipment in room 204 produces erratic signal peaks",
        "category_id": cat.id,
        "priority": "high",
        "is_anonymous": "false"
    }

    resp = client.post("/api/cases", data=data, files=files)
    assert resp.status_code == 201
    res_data = resp.json()
    assert "case_id" in res_data
    assert res_data["ref_id"].startswith("VP-2026-")
    assert res_data["claim_code"] is None

    # verify case details endpoint
    case_id = res_data["case_id"]
    detail_resp = client.get(f"/api/cases/{case_id}")
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["title"] == "Broken laboratory spectrometer"
    assert len(detail["attachments"]) == 1
    assert detail["attachments"][0]["filename"] == "test_doc.pdf"
    assert len(detail["events"]) == 1
    assert detail["events"][0]["type"] == "CASE_FILED"

def test_case_lifecycle_via_api(client, fixtures):
    official = fixtures["official"]
    cat = fixtures["category"]
    token = create_access_token(data={"sub": official.id, "role": official.role})
    client.cookies.set("access_token", token)

    # 1. file case
    resp = client.post(
        "/api/cases",
        data={"title": "Grade dispute", "description": "Need review", "category_id": cat.id}
    )
    case_id = resp.json()["case_id"]

    # 2. assign case
    assign_resp = client.post(f"/api/cases/{case_id}/assign", json={"assignee_id": official.id})
    assert assign_resp.status_code == 200
    assert assign_resp.json()["state"] == "Assigned"

    # 3. transition to in review
    review_resp = client.post(f"/api/cases/{case_id}/transition", json={"to_state": "In Review"})
    assert review_resp.status_code == 200
    assert review_resp.json()["state"] == "In Review"

    # 4. post comment
    comment_resp = client.post(
        f"/api/cases/{case_id}/comments",
        json={"text": "Reviewing grade sheets in faculty office"}
    )
    assert comment_resp.status_code == 200
    assert comment_resp.json()["seq"] == 4

    # 5. transition to resolved
    resolve_resp = client.post(
        f"/api/cases/{case_id}/transition",
        json={"to_state": "Resolved", "note": "Grade correction applied"}
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["state"] == "Resolved"

    # 6. verify integrity
    verify_resp = client.get(f"/api/cases/{case_id}/verify")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["valid"] is True
    assert verify_resp.json()["checked"] == 5

def test_unsupported_file_type_rejected(client, fixtures):
    cat = fixtures["category"]
    files = [
        ("files", ("evil.exe", io.BytesIO(b"executable content"), "application/x-msdownload"))
    ]
    data = {
        "title": "Malware attempt",
        "description": "Upload dangerous binary",
        "category_id": cat.id
    }
    resp = client.post("/api/cases", data=data, files=files)
    assert resp.status_code == 400
    assert "not allowed" in resp.json()["detail"]

