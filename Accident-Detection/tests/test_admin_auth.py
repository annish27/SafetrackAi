import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("accident_main", Path(__file__).resolve().parents[1] / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app


def test_admin_dashboard_requires_login():
    client = app.test_client()
    response = client.get("/admin/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")


def test_admin_login_success_sets_session():
    client = app.test_client()
    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")
    with client.session_transaction() as session:
        assert session.get("is_admin") is True
