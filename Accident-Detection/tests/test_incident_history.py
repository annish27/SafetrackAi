import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("accident_main", Path(__file__).resolve().parents[1] / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

app = module.app


def test_record_incident_creates_entry():
    incident_id = module.record_incident(
        severity="HIGH SEVERITY",
        location="19.070, 72.877",
        weather="rain",
        temperature=28.4,
        status="active",
        summary="Collision detected near the city center.",
    )
    assert incident_id is not None


def test_admin_incident_history_is_protected():
    client = app.test_client()
    response = client.get("/admin/incidents", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/login")
