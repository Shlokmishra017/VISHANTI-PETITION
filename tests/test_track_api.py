import pytest
from app.routers import track

def test_anonymous_flow_and_tracking(client, fixtures):
    cat = fixtures["category"]

    # 1. file anonymous case
    data = {
        "title": "Anonymous grievance regarding library noise",
        "description": "Late night disturbance on 3rd floor reading hall",
        "category_id": cat.id,
        "priority": "low",
        "is_anonymous": "true"
    }
    resp = client.post("/api/cases", data=data)
    assert resp.status_code == 201
    res = resp.json()
    claim_code = res["claim_code"]
    assert claim_code is not None

    # 2. track case using claim code
    track_resp = client.post("/api/track", json={"claim_code": claim_code})
    assert track_resp.status_code == 200
    track_data = track_resp.json()
    assert track_data["case"]["title"] == "Anonymous grievance regarding library noise"
    assert track_data["verification"]["valid"] is True
    assert len(track_data["events"]) == 1

    # 3. post comment anonymously
    comment_resp = client.post(
        "/api/track/comments",
        json={"claim_code": claim_code, "text": "Noise continued again tonight until 2 AM"}
    )
    assert comment_resp.status_code == 200

    # 4. verify ledger shows pseudonymous actor ref only
    track_again = client.post("/api/track", json={"claim_code": claim_code})
    events = track_again.json()["events"]
    assert len(events) == 2
    second_event = events[1]
    assert second_event["actor_ref"].startswith("anon_")
    assert " Rahul " not in second_event["actor_ref"]

def test_invalid_claim_code_returns_generic_404(client):
    resp = client.post("/api/track", json={"claim_code": "INVALIDCLAIMCODE123"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Case not found"

def test_track_rate_limiting(client):
    # clear rate limit storage to start clean
    track._rate_limit_records.clear()

    # make 5 allowed requests
    for _ in range(5):
        resp = client.post("/api/track", json={"claim_code": "NONEXISTENTCODE"})
        assert resp.status_code == 404

    # 6th request within window must return 429
    rate_limited_resp = client.post("/api/track", json={"claim_code": "NONEXISTENTCODE"})
    assert rate_limited_resp.status_code == 429

