"""Use case "Visualizar información del producto" for external users (v1.1.0)."""

from tests.conftest import API, example


def test_product_info_is_public_and_flags_pending_copy(client):
    r = client.get(f"{API}/public/product-info")
    assert r.status_code == 200
    assert r.headers["cache-control"].startswith("public")
    body = r.json()
    assert set(body) == set(example("product_info.response.200.json"))
    assert body["name"] == "NEUROPHOBIA"
    assert body["contentStatus"] == "pendiente_de_aprobacion"
    assert "no sustituye" in body["disclaimer"]


def test_product_info_steps_include_phobia_grade_adjustment(client):
    steps = client.get(f"{API}/public/product-info").json()["howItWorks"]
    assert [s["order"] for s in steps] == list(range(1, len(steps) + 1))
    assert any("grado de fobia" in s["title"].lower() for s in steps)
