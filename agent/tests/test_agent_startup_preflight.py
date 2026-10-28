from agent.api.client import APIClientAdapter
from agent.config.settings import AgentConfig
from agent.core.api.client import DEFAULT_API_URL


def test_agent_defaults_target_local_fastapi_backend(monkeypatch):
    monkeypatch.delenv("API_URL", raising=False)
    assert AgentConfig().api_url == DEFAULT_API_URL == "http://127.0.0.1:8000"


def test_backend_health_check_accepts_healthy_and_degraded_responses():
    client = APIClientAdapter.__new__(APIClientAdapter)
    client._make_request = lambda *args, **kwargs: {"status": "healthy"}
    assert client.is_backend_available() is True

    client._make_request = lambda *args, **kwargs: {"status": "degraded"}
    assert client.is_backend_available() is True


def test_backend_health_check_returns_false_for_connection_failure():
    client = APIClientAdapter.__new__(APIClientAdapter)

    def fail(*args, **kwargs):
        raise OSError("connection refused")

    client._make_request = fail
    assert client.is_backend_available() is False
