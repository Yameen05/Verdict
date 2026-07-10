def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_config_status_does_not_expose_secret_values(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("FINNHUB_API_KEY", "secret-finnhub")
    monkeypatch.setenv("FRED_API_KEY", "secret-fred")
    get_settings.cache_clear()
    response = client.get("/health/config")
    assert response.status_code == 200
    body = response.json()
    assert body["sources"]["signals"]["finnhub"] is True
    assert body["sources"]["signals"]["fred"] is True
    assert "secret" not in response.text
    get_settings.cache_clear()
