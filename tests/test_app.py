"""
Testes básicos do PDF AI Service.
"""
import pytest
from backend import create_app


@pytest.fixture
def client():
    """Cria um test client Flask."""
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    """Testa o endpoint /health."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "pdf-service"
    assert "version" in data


def test_health_llm(client):
    """GET /health/llm devolve JSON com estado do probe (sempre 200)."""
    res = client.get("/health/llm")
    assert res.status_code == 200
    data = res.get_json()
    assert "reachable" in data
    assert "probe_url" in data
    assert "configured_model" in data


def test_analyze_no_file(client):
    """Testa /analyze sem enviar arquivo."""
    res = client.post("/analyze")
    assert res.status_code == 400
    data = res.get_json()
    assert "error" in data


def test_analyze_invalid_file(client):
    """Testa /analyze com arquivo não-PDF."""
    import io
    data = {"file": (io.BytesIO(b"not a pdf"), "test.txt")}
    res = client.post("/analyze", data=data, content_type="multipart/form-data")
    assert res.status_code == 400
