"""Smoke test: the dashboard starts and shows its numbers without errors."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def test_dashboard_runs_with_demo_data():
    at = AppTest.from_file(APP, default_timeout=60).run()
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert "Money missing" in labels
    assert "Anomalies" in labels
