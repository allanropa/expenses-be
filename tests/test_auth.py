def register(client, email="ana@example.com"):
    return client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse", "display_name": "Ana"},
    )


def test_register_creates_session_and_default_settings(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "ana@example.com"
    assert body["csrf_token"]

    settings = client.get("/api/settings")
    assert settings.status_code == 200
    assert settings.json() == {"reporting_currency": "COP", "timezone": "America/Bogota"}


def test_duplicate_email_is_rejected(client):
    assert register(client).status_code == 201
    assert register(client).status_code == 409


def test_protected_mutations_require_csrf(client):
    register(client)
    response = client.patch("/api/auth/profile", json={"display_name": "Nuevo"})
    assert response.status_code == 403

    session = client.get("/api/auth/session").json()
    response = client.patch(
        "/api/auth/profile",
        headers={"X-CSRF-Token": session["csrf_token"]},
        json={"display_name": "Nuevo"},
    )
    assert response.status_code == 200
    assert response.json()["display_name"] == "Nuevo"


def test_users_cannot_use_another_users_session(client):
    register(client, "first@example.com")
    first_session = client.cookies.get("expenses_session")
    client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": client.get("/api/auth/session").json()["csrf_token"]},
    )
    register(client, "second@example.com")
    second_session = client.cookies.get("expenses_session")
    assert first_session != second_session

    client.cookies.set("expenses_session", first_session)
    session = client.get("/api/auth/session")
    assert session.status_code == 401


def test_login_and_password_change(client):
    register(client)
    client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": client.get("/api/auth/session").json()["csrf_token"]},
    )
    login = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct horse"})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    changed = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": "correct horse", "new_password": "new password"},
    )
    assert changed.status_code == 204


def test_password_change_revokes_other_sessions(client):
    register(client)
    csrf = client.get("/api/auth/session").json()["csrf_token"]
    first_session = client.cookies.get("expenses_session")

    login = client.post("/api/auth/login", json={"email": "ana@example.com", "password": "correct horse"})
    assert login.status_code == 200
    second_session = client.cookies.get("expenses_session")

    client.cookies.set("expenses_session", first_session)

    changed = client.post(
        "/api/auth/password",
        headers={"X-CSRF-Token": csrf},
        json={"current_password": "correct horse", "new_password": "new password"},
    )
    assert changed.status_code == 204
    client.cookies.set("expenses_session", second_session)
    assert client.get("/api/auth/session").status_code == 401


def test_login_is_rate_limited_after_repeated_failures(client):
    register(client)
    for _ in range(10):
        response = client.post(
            "/api/auth/login",
            json={"email": "ana@example.com", "password": "wrong password"},
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/auth/login",
        json={"email": "ana@example.com", "password": "wrong password"},
    )
    assert limited.status_code == 429
