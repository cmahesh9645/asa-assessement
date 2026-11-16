import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from database import Base, get_db  # noqa: E402
from main import app  # noqa: E402

TEST_DB_URL = "sqlite:///./test_vulntracker.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def register_and_login(username="alice", email="alice@example.com", password="password123"):
    client.post("/auth/register", json={"username": username, "email": email, "password": password})
    resp = client.post("/auth/login", json={"username": username, "password": password})
    return resp.json()["access_token"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_register_user():
    resp = client.post("/auth/register", json={
        "username": "bob",
        "email": "bob@example.com",
        "password": "secret",
    })
    assert resp.status_code == 201
    assert resp.json()["username"] == "bob"


def test_register_duplicate_username():
    payload = {"username": "bob", "email": "bob@example.com", "password": "secret"}
    client.post("/auth/register", json=payload)
    resp = client.post("/auth/register", json={**payload, "email": "bob2@example.com"})
    assert resp.status_code == 400


def test_login_success():
    client.post("/auth/register", json={"username": "alice", "email": "alice@example.com", "password": "pw"})
    resp = client.post("/auth/login", json={"username": "alice", "password": "pw"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password():
    client.post("/auth/register", json={"username": "alice", "email": "alice@example.com", "password": "pw"})
    resp = client.post("/auth/login", json={"username": "alice", "password": "wrong"})
    assert resp.status_code == 401


def test_create_scan():
    token = register_and_login()
    resp = client.post("/scans", json={
        "title": "Reflected XSS in search",
        "description": "User input is echoed without sanitisation",
        "severity": "high",
        "affected_component": "GET /search",
    }, headers=auth_headers(token))
    assert resp.status_code == 201
    assert resp.json()["title"] == "Reflected XSS in search"


def test_list_scans():
    token = register_and_login()
    client.post("/scans", json={
        "title": "Test finding",
        "severity": "low",
        "affected_component": "misc",
    }, headers=auth_headers(token))
    resp = client.get("/scans", headers=auth_headers(token))
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_search_scans():
    # TODO: add assertions for search results
    token = register_and_login()
    client.post("/scans", json={
        "title": "SQL Injection via login",
        "severity": "critical",
        "affected_component": "POST /auth/login",
    }, headers=auth_headers(token))
    resp = client.get("/scans/search?q=SQL", headers=auth_headers(token))
    assert resp.status_code == 200


def test_update_scan_status():
    token = register_and_login()
    scan_id = client.post("/scans", json={
        "title": "Open redirect",
        "severity": "medium",
        "affected_component": "redirect handler",
    }, headers=auth_headers(token)).json()["id"]

    resp = client.patch(f"/scans/{scan_id}", json={"status": "in_progress"}, headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


def test_delete_scan():
    token = register_and_login()
    scan_id = client.post("/scans", json={
        "title": "Stale finding",
        "severity": "low",
        "affected_component": "misc",
    }, headers=auth_headers(token)).json()["id"]

    resp = client.delete(f"/scans/{scan_id}", headers=auth_headers(token))
    assert resp.status_code == 204


def test_share_link_returns_scan_without_auth():
    token = register_and_login()
    headers = auth_headers(token)
    scan = client.post("/scans", json={
        "title": "Shared finding", "severity": "high", "affected_component": "api"
    }, headers=headers).json()
    response = client.post(f"/scans/{scan['id']}/share", json={}, headers=headers)
    assert response.status_code == 200
    share_url = response.json()["share_url"]
    public_response = client.get(share_url.replace("http://testserver", ""))
    assert public_response.status_code == 200
    assert public_response.json()["id"] == scan["id"]


def test_share_link_password_and_expiry():
    from datetime import datetime, timedelta
    import hashlib
    from models import ShareLink

    token = register_and_login()
    headers = auth_headers(token)
    scan = client.post("/scans", json={
        "title": "Protected finding", "severity": "critical", "affected_component": "api"
    }, headers=headers).json()
    response = client.post(
        f"/scans/{scan['id']}/share", json={"password": "correct-horse"}, headers=headers
    )
    share_token = response.json()["share_url"].rsplit("/", 1)[1]
    assert client.get(f"/share/{share_token}").status_code == 403
    assert client.get(f"/share/{share_token}?password=wrong-password").status_code == 403
    assert client.get(f"/share/{share_token}?password=correct-horse").status_code == 200

    db = TestingSessionLocal()
    link = db.query(ShareLink).filter(
        ShareLink.token_hash == hashlib.sha256(share_token.encode()).hexdigest()
    ).one()
    link.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db.commit()
    db.close()
    assert client.get(f"/share/{share_token}?password=correct-horse").status_code == 404


def test_user_cannot_read_or_share_another_users_scan():
    owner_token = register_and_login("owner", "owner@example.com")
    other_token = register_and_login("other", "other@example.com")
    scan = client.post("/scans", json={
        "title": "Private finding", "severity": "high", "affected_component": "api"
    }, headers=auth_headers(owner_token)).json()
    assert client.get(f"/scans/{scan['id']}", headers=auth_headers(other_token)).status_code == 404
    assert client.post(
        f"/scans/{scan['id']}/share", json={}, headers=auth_headers(other_token)
    ).status_code == 404
