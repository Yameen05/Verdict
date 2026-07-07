"""Production configuration must fail closed when security controls are unsafe."""

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from app.config import Settings


def test_production_rejects_insecure_defaults():
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(_env_file=None, environment="production")


def test_production_accepts_explicit_secure_configuration():
    settings = Settings(
        _env_file=None,
        environment="production",
        session_cookie_secure=True,
        docs_enabled=False,
        cors_origins="https://verdict.example.com",
        allowed_hosts="verdict.example.com",
        auth_bootstrap_token="a" * 48,
        auth_encryption_key=Fernet.generate_key().decode("ascii"),
    )

    assert settings.session_cookie_name == "__Host-verdict_session"


class TestResolvedEmbeddingKey:
    def test_defaults_to_openai_key(self, monkeypatch):
        from app.config import Settings

        s = Settings(openai_api_key="sk-openai", _env_file=None)
        assert s.resolved_embedding_key == "sk-openai"

    def test_explicit_embedding_key_wins(self):
        from app.config import Settings

        s = Settings(
            openai_api_key="sk-openai",
            embedding_api_key="emb-key",
            embedding_base_url="https://example/v1",
            _env_file=None,
        )
        assert s.resolved_embedding_key == "emb-key"

    def test_reuses_llm_key_when_base_urls_match(self):
        from app.config import Settings

        url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        s = Settings(
            llm_base_url=url,
            llm_api_key="gemini-key",
            embedding_base_url=url,
            _env_file=None,
        )
        assert s.resolved_embedding_key == "gemini-key"

    def test_custom_base_without_key_resolves_empty(self):
        from app.config import Settings

        s = Settings(
            openai_api_key="sk-openai",
            embedding_base_url="https://other-provider/v1",
            _env_file=None,
        )
        # Never hand an sk- key to a non-OpenAI endpoint.
        assert s.resolved_embedding_key == ""
