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
