"""The deployment posture, as assertions.

Everything here is about the difference between "runs on my laptop" and "is
safe to give someone a link to".  The load-bearing case is the first class:
curated mode must actually refuse source, or the whole argument in
docs/20-deployment.md for publishing without a container is false.
"""

from __future__ import annotations

import importlib
import time

import pytest
from fastapi.testclient import TestClient

from algostudio import config as config_module


def _client(monkeypatch, **env: str) -> TestClient:
    """A fresh app with a fresh Settings, since SETTINGS is read at import."""
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    importlib.reload(config_module)
    from algostudio.api import app as app_module
    importlib.reload(app_module)
    return TestClient(app_module.create_app())


@pytest.fixture(autouse=True)
def _restore_settings():
    yield
    importlib.reload(config_module)
    from algostudio.api import app as app_module
    importlib.reload(app_module)


class TestCuratedMode:
    def test_arbitrary_source_is_refused(self, monkeypatch):
        client = _client(monkeypatch, ALGOSTUDIO_ALLOW_ARBITRARY_CODE="0")
        response = client.post("/api/v1/executions", json={"source": "x = 1"})
        assert response.status_code == 403
        assert response.json()["type"].endswith("arbitrary-code-disabled")

    def test_analysis_is_refused_too(self, monkeypatch):
        # Analysis does not execute, but it does instrument visitor source, and
        # leaving it open would expose the transformer to input the rest of the
        # deployment has decided not to accept.
        client = _client(monkeypatch, ALGOSTUDIO_ALLOW_ARBITRARY_CODE="0")
        assert client.post("/api/v1/analyze", json={"source": "x = 1"}).status_code == 403

    def test_the_catalogue_still_runs(self, monkeypatch):
        # If this breaks, curated mode is not a deployment mode, it is an
        # outage: the bundled algorithms are the entire product in that mode.
        client = _client(monkeypatch, ALGOSTUDIO_ALLOW_ARBITRARY_CODE="0")
        response = client.post("/api/v1/algorithms/bubble_sort/run", json={"inputs": {}})
        assert response.status_code == 201
        assert response.json()["status"] == "ok"
        assert response.json()["event_count"] > 0

    def test_health_advertises_the_mode(self, monkeypatch):
        # The SPA disables its editor from this field.
        client = _client(monkeypatch, ALGOSTUDIO_ALLOW_ARBITRARY_CODE="0")
        assert client.get("/api/v1/health").json()["allow_arbitrary_code"] is False

    def test_default_is_permissive(self, monkeypatch):
        client = _client(monkeypatch, ALGOSTUDIO_ALLOW_ARBITRARY_CODE="1")
        assert client.post("/api/v1/executions", json={"source": "x = 1"}).status_code == 201


class TestCors:
    def test_wildcard_by_default(self, monkeypatch):
        client = _client(monkeypatch, ALGOSTUDIO_CORS_ORIGINS="*")
        response = client.get("/api/v1/health", headers={"Origin": "http://other.test"})
        assert response.headers.get("access-control-allow-origin") == "*"

    def test_none_installs_no_middleware(self, monkeypatch):
        # The single-container deployment serves the SPA from this same origin,
        # so no browser needs a grant and none is issued.
        client = _client(monkeypatch, ALGOSTUDIO_CORS_ORIGINS="none")
        response = client.get("/api/v1/health", headers={"Origin": "http://other.test"})
        assert "access-control-allow-origin" not in response.headers

    def test_explicit_origin_is_not_a_wildcard(self, monkeypatch):
        client = _client(monkeypatch, ALGOSTUDIO_CORS_ORIGINS="https://algo.example")
        allowed = client.get("/api/v1/health",
                             headers={"Origin": "https://algo.example"})
        denied = client.get("/api/v1/health", headers={"Origin": "http://other.test"})
        assert allowed.headers.get("access-control-allow-origin") == "https://algo.example"
        assert "access-control-allow-origin" not in denied.headers


class TestDeploymentWarnings:
    def test_subprocess_plus_arbitrary_code_is_flagged(self, monkeypatch):
        monkeypatch.setenv("ALGOSTUDIO_ALLOW_ARBITRARY_CODE", "1")
        monkeypatch.setenv("ALGOSTUDIO_SANDBOX", "subprocess")
        importlib.reload(config_module)
        warnings = config_module.Settings().deployment_warnings()
        assert any("boundary" in w for w in warnings)

    def test_docker_plus_explicit_cors_is_clean(self, monkeypatch):
        monkeypatch.setenv("ALGOSTUDIO_ALLOW_ARBITRARY_CODE", "1")
        monkeypatch.setenv("ALGOSTUDIO_SANDBOX", "docker")
        monkeypatch.setenv("ALGOSTUDIO_CORS_ORIGINS", "none")
        importlib.reload(config_module)
        assert config_module.Settings().deployment_warnings() == []


class TestRetention:
    def test_expired_executions_are_removed_with_their_directories(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ALGOSTUDIO_DATA", str(tmp_path))
        importlib.reload(config_module)
        from algostudio.services import execution_service
        importlib.reload(execution_service)

        service = execution_service.ExecutionService()
        result = service.run_algorithm("bubble_sort", granularity="minimal")
        record = service.db.get_execution(result.execution_id)
        storage = tmp_path / "executions" / result.execution_id

        assert storage.is_dir()
        assert service.purge_expired(days=14) == 0        # far too new to expire

        # Backdate it past the window rather than sleeping.
        with service.db.connect() as conn:
            conn.execute("UPDATE execution SET created_at = ? WHERE id = ?",
                         (time.time() - 30 * 86_400, result.execution_id))

        assert service.purge_expired(days=14) == 1
        assert service.db.get_execution(result.execution_id) is None
        assert not storage.exists(), "the recording directory must go with the row"
        assert record["storage_dir"]

    def test_zero_days_disables_expiry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ALGOSTUDIO_DATA", str(tmp_path))
        importlib.reload(config_module)
        from algostudio.services import execution_service
        importlib.reload(execution_service)

        service = execution_service.ExecutionService()
        service.run_algorithm("bubble_sort", granularity="minimal")
        with service.db.connect() as conn:
            conn.execute("UPDATE execution SET created_at = 0")
        assert service.purge_expired(days=0) == 0
        assert service.db.list_executions(10)
