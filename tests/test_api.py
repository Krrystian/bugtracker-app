def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok"}
    assert r.headers["X-Content-Type-Options"] == "nosniff"


def test_bugs_require_auth(client):
    assert client.get("/bugs").status_code == 401
    assert client.post("/bugs", json={"title": "x"}).status_code == 401


def test_register_duplicate_and_bad_login(client):
    body = {"email": "bob@example.com", "password": "correct-horse-battery"}
    assert client.post("/auth/register", json=body).status_code == 201
    assert client.post("/auth/register", json=body).status_code == 409
    bad = {**body, "password": "wrong-password-123"}
    assert client.post("/auth/login", json=bad).status_code == 401


def test_crud(client, auth):
    h = auth()
    r = client.post("/bugs", json={"title": "Crash", "priority": "high"}, headers=h)
    assert r.status_code == 201
    bug_id = r.json()["id"]

    assert client.get(f"/bugs/{bug_id}", headers=h).json()["title"] == "Crash"
    assert len(client.get("/bugs", headers=h).json()) == 1

    r = client.patch(f"/bugs/{bug_id}", json={"status": "closed"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "closed"

    assert client.delete(f"/bugs/{bug_id}", headers=h).status_code == 204
    assert client.get(f"/bugs/{bug_id}", headers=h).status_code == 404


def test_only_reporter_can_modify(client, auth):
    alice, mallory = auth("alice@example.com"), auth("mallory@example.com")
    bug_id = client.post("/bugs", json={"title": "Mine"}, headers=alice).json()["id"]
    assert client.patch(f"/bugs/{bug_id}", json={"title": "x"}, headers=mallory).status_code == 403
    assert client.delete(f"/bugs/{bug_id}", headers=mallory).status_code == 403


def test_sql_injection_payload_is_just_data(client, auth):
    h = auth()
    payload = "x'; DROP TABLE bugs; --"
    r = client.post("/bugs", json={"title": payload}, headers=h)
    assert r.status_code == 201
    assert client.get("/bugs", headers=h).json()[0]["title"] == payload


def test_invalid_token(client):
    r = client.get("/bugs", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
