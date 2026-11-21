import importlib.util
import os
from pathlib import Path

spec = importlib.util.spec_from_file_location("accident_main", Path(__file__).resolve().parents[1] / "main.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_build_route_plan_returns_service_order():
    route_plan = module.build_route_plan(
        (19.070, 72.877),
        [
            {"name": "City Police Station", "lat": 19.072, "lon": 72.875},
            {"name": "General Hospital", "lat": 19.075, "lon": 72.88},
        ],
    )
    assert len(route_plan) >= 2
    assert route_plan[0]["type"] in {"police", "hospital"}
    assert route_plan[0]["distance_km"] >= 0


def test_generate_report_pdf_creates_file(tmp_path):
    output_path = tmp_path / "report.pdf"
    created = module.generate_report_pdf(str(output_path), "HIGH SEVERITY", "19.070, 72.877", "rain", 29.5, "Collision detected near city center")
    assert created is True
    assert output_path.exists()
    assert output_path.stat().st_size > 0
