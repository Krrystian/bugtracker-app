import re

PASSWORD = "correct-horse-battery"


def _csrf(client, path):
    html = client.get(path).text
    return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)


def _web_login(client, email="alice@example.com"):
    client.post(
        "/ui/register",
        data={"email": email, "password": PASSWORD, "csrf_token": _csrf(client, "/ui/register")},
    )
    r = client.post(
        "/ui/login",
        data={"email": email, "password": PASSWORD, "csrf_token": _csrf(client, "/ui/login")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    return _csrf(client, "/ui")


def test_root_redirects_and_list_requires_login(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/ui"
    r = client.get("/ui", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/ui/login"


def test_login_page_has_strict_csp(client):
    r = client.get("/ui/login")
    assert r.status_code == 200
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]


def test_session_cookie_is_httponly_strict(client):
    _web_login(client)
    cookie = next(c for c in client.cookies.jar if c.name == "session")
    assert cookie.has_nonstandard_attr("HttpOnly")
    assert cookie.get_nonstandard_attr("SameSite").lower() == "strict"


def test_post_without_csrf_is_rejected(client):
    _web_login(client)
    r = client.post("/ui/bugs/new", data={"title": "x"})
    assert r.status_code == 403


def test_web_crud(client):
    csrf = _web_login(client)
    r = client.post(
        "/ui/bugs/new",
        data={"title": "Broken button", "priority": "high", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    url = r.headers["location"]
    assert "Broken button" in client.get(url).text

    r = client.post(
        f"{url}/edit",
        data={"title": "Broken button", "priority": "low", "status": "closed", "csrf_token": csrf},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "status-closed" in client.get(url).text

    client.post(f"{url}/delete", data={"csrf_token": csrf})
    assert client.get(url).status_code == 404


def test_html_is_escaped(client):
    csrf = _web_login(client)
    payload = "<script>alert(1)</script>"
    client.post("/ui/bugs/new", data={"title": payload, "csrf_token": csrf})
    html = client.get("/ui").text
    assert payload not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_other_user_cannot_edit_via_web(client):
    csrf = _web_login(client, "alice@example.com")
    url = client.post(
        "/ui/bugs/new", data={"title": "Mine", "csrf_token": csrf}, follow_redirects=False
    ).headers["location"]
    client.cookies.clear()
    csrf = _web_login(client, "mallory@example.com")
    assert client.get(f"{url}/edit").status_code == 403
    r = client.post(f"{url}/delete", data={"csrf_token": csrf})
    assert r.status_code == 403
