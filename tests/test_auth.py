from app.auth import hash_password, verify_password, create_access_token
from app.scope import can_access_case

def test_argon2_password_hashing():
    pwd = "secure_password_123"
    hashed = hash_password(pwd)

    # verify valid password succeeds
    assert verify_password(pwd, hashed) is True

    # verify wrong password fails
    assert verify_password("wrong_password", hashed) is False

def test_login_logout_flow(client, fixtures):
    # 1. login with valid credentials
    resp = client.post(
        "/api/auth/login",
        json={"email": "student@test.edu", "password": "pass123"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user"]["email"] == "student@test.edu"
    assert data["user"]["role"] == "student"
    assert "access_token" in resp.cookies

    # 2. get current authenticated user profile
    me_resp = client.get("/api/auth/me", cookies=resp.cookies)
    assert me_resp.status_code == 200
    assert me_resp.json()["user"]["email"] == "student@test.edu"

    # 3. logout and ensure cookie is cleared
    logout_resp = client.post("/api/auth/logout", cookies=resp.cookies)
    assert logout_resp.status_code == 204

def test_login_invalid_credentials_returns_401(client, fixtures):
    # login with invalid password must be rejected
    resp = client.post(
        "/api/auth/login",
        json={"email": "student@test.edu", "password": "wrongpassword"}
    )
    assert resp.status_code == 401
    assert "Invalid email or password" in resp.json()["detail"]

def test_scope_visibility_rules(fixtures):
    case = fixtures["case"]
    student = fixtures["student"]
    official = fixtures["official"]
    other_official = fixtures["other_official"]
    admin = fixtures["admin"]

    # student who filed case can access
    assert can_access_case(student, case) is True

    # official from case department can access
    assert can_access_case(official, case) is True

    # official from other department cannot access
    assert can_access_case(other_official, case) is False

    # admin can access all cases
    assert can_access_case(admin, case) is True

