def register(client, email="ana@example.com"):
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "correct horse", "display_name": "Ana"},
    )
    assert response.status_code == 201
    return response.json()["csrf_token"]


def test_new_users_receive_default_categories(client):
    register(client)

    response = client.get("/api/categories")

    assert response.status_code == 200
    assert {category["name"] for category in response.json()} == {
        "Alimentación",
        "Vivienda",
        "Transporte",
        "Salud",
        "Entretenimiento",
        "Servicios",
        "Salario",
        "Otros ingresos",
        "Otros gastos",
    }


def test_user_can_create_and_archive_a_category(client):
    csrf = register(client)

    created = client.post(
        "/api/categories",
        headers={"X-CSRF-Token": csrf},
        json={"name": "  Mascotas  ", "kind": "expense"},
    )
    assert created.status_code == 201
    assert created.json()["name"] == "Mascotas"
    assert created.json()["kind"] == "expense"

    archived = client.delete(
        f"/api/categories/{created.json()['id']}",
        headers={"X-CSRF-Token": csrf},
    )
    assert archived.status_code == 204
    assert "Mascotas" not in {category["name"] for category in client.get("/api/categories").json()}


def test_category_name_cannot_be_only_whitespace(client):
    csrf = register(client)

    response = client.post(
        "/api/categories",
        headers={"X-CSRF-Token": csrf},
        json={"name": "   ", "kind": "both"},
    )

    assert response.status_code == 422
