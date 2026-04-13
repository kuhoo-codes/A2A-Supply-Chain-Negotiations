from pathlib import Path

from fastapi.testclient import TestClient

from backend.app.core.config import get_settings
from backend.app.main import app


def _configure_storage(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("A2A_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("A2A_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("A2A_EXPORTS_DIR", str(tmp_path / "exports"))
    get_settings.cache_clear()


def test_health_and_empty_runs(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/runs").json() == []


def test_simulation_run_requires_openai_without_creating_runs(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post("/simulation/run", json={"seed": 42})

    assert response.status_code == 503
    assert response.json()["detail"] == "OPENAI_API_KEY is not configured."
    assert not list((tmp_path / "runs").glob("*.json"))


def test_pipeline_test_reports_missing_openai_cleanly(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)
    client = TestClient(app)

    response = client.post("/simulation/test-pipeline", json={"seed": 42})
    payload = response.json()

    assert response.status_code == 200
    assert payload["success"] is False
    assert payload["run_id"] == ""
    assert payload["openai"] == {
        "configured": False,
        "available": False,
        "message": "OPENAI_API_KEY is not configured.",
    }
    assert not list((tmp_path / "runs").glob("*.json"))
