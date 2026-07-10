import base64
import binascii
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", description="OpenAI API key")

    # Optional. When set, filing vectors go to Pinecone serverless; when blank
    # (the default) they live in a local SQLite file — zero external setup.
    pinecone_api_key: str = Field(default="", description="Pinecone API key")
    vector_db_path: str = Field(
        default="./data/vectors.db",
        description="SQLite file for the local vector store backend",
    )
    pinecone_index_name: str = Field(default="verdict-filings")
    pinecone_cloud: str = Field(default="aws")
    pinecone_region: str = Field(default="us-east-1")

    sec_user_agent: str = Field(
        default="Verdict Research contact@example.com",
        description="SEC EDGAR requires a descriptive User-Agent with contact info.",
    )

    news_api_key: str = Field(default="", description="NewsAPI.org key for the news agent")
    news_lookback_days: int = Field(default=30, ge=1, le=30)
    news_max_articles: int = Field(default=30, ge=1, le=100)

    # --- Optional market-signal providers (all key-gated; blank = skipped) ---
    # Each adds a distinct signal to the timing agent and degrades gracefully.
    alphavantage_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("ALPHAVANTAGE_API_KEY", "ALPHA_VANTAGE_API_KEY"),
        description="Alpha Vantage: fundamentals overview",
    )
    finnhub_api_key: str = Field(default="", description="Finnhub: analyst ratings, earnings, quote")
    polygon_api_key: str = Field(default="", description="Polygon.io: quote/prev-close")
    tiingo_api_key: str = Field(default="", description="Tiingo: daily price")
    fred_api_key: str = Field(default="", description="FRED (St. Louis Fed): macro regime")
    # Retail sentiment calls are public/best-effort; toggle off if they become noisy.
    stocktwits_enabled: bool = Field(default=True)
    reddit_enabled: bool = Field(default=True)
    reddit_user_agent: str = Field(default="VerdictResearch/1.0")
    # How long aggregated market signals are cached (seconds).
    signals_cache_seconds: int = Field(default=300, ge=0)

    @property
    def signal_sources_configured(self) -> list[str]:
        """Provider names whose credentials are present (or that need none)."""
        out: list[str] = []
        if self.finnhub_api_key.strip():
            out.append("finnhub")
        if self.alphavantage_api_key.strip():
            out.append("alphavantage")
        if self.polygon_api_key.strip():
            out.append("polygon")
        if self.tiingo_api_key.strip():
            out.append("tiingo")
        if self.fred_api_key.strip():
            out.append("fred")
        if self.stocktwits_enabled:
            out.append("stocktwits")
        if self.reddit_enabled:
            out.append("reddit")
        return out

    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dim: int = Field(default=1536)
    # Optional OpenAI-compatible endpoint for embeddings. Blank uses OpenAI.
    # Gemini's compatibility layer serves embeddings too (model:
    # gemini-embedding-001), so one free Gemini key can power the whole app.
    embedding_base_url: str = Field(default="")
    embedding_api_key: str = Field(default="")
    llm_model: str = Field(default="gpt-4o-mini")

    # --- LLM provider routing (OpenAI-compatible endpoints) ---
    # Leave blank to call api.openai.com. To use a different provider that
    # speaks the OpenAI API, set its base URL here and point LLM_MODEL at one of
    # that provider's models. Examples:
    #   Google Gemini : https://generativelanguage.googleapis.com/v1beta/openai/   (model: gemini-2.5-flash)
    #   Groq          : https://api.groq.com/openai/v1                              (model: llama-3.3-70b-versatile)
    llm_base_url: str = Field(default="")
    # API key for the LLM provider. If blank, falls back to openai_api_key so
    # existing OpenAI-only setups keep working with no env changes.
    llm_api_key: str = Field(default="")

    # USD per 1M tokens for cost tracking. Defaults target OpenAI
    # gpt-4o-mini / text-embedding-3-small. Override when you swap providers.
    cost_input_per_mtok_usd: float = Field(default=0.15)
    cost_output_per_mtok_usd: float = Field(default=0.60)
    cost_embed_per_mtok_usd: float = Field(default=0.02)

    cors_origins: str = Field(default="http://localhost:5173")

    # --- Production ops ---
    environment: Literal["development", "test", "production"] = Field(default="development")
    log_level: str = Field(default="INFO")
    allowed_hosts: str = Field(default="localhost,127.0.0.1,testserver")
    docs_enabled: bool = Field(default=True)

    # --- Owner authentication ---
    # One-time secret required only to create the first owner account.
    auth_bootstrap_token: str = Field(default="")
    # Fernet key used to encrypt the TOTP seed. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    auth_encryption_key: str = Field(default="")
    session_cookie_secure: bool = Field(default=False)
    session_ttl_hours: int = Field(default=12, ge=1, le=168)
    session_idle_minutes: int = Field(default=30, ge=5, le=1440)
    login_challenge_minutes: int = Field(default=5, ge=1, le=15)
    require_2fa: bool = Field(default=True)

    # --- Free-tier protection: shared run cache + daily quotas ---
    # A research run for a ticker is served to everyone from the most recent
    # stored run within this window instead of re-running the pipeline
    # (?fresh=true bypasses). Zero LLM cost for cache hits.
    research_cache_minutes: int = Field(default=360, ge=0)
    # Fresh (non-cached) runs allowed per user and across all users per UTC day.
    daily_runs_per_user: int = Field(default=10, ge=1)
    daily_runs_global: int = Field(default=40, ge=1)

    # --- Server-side alert evaluation ---
    # How often the background worker checks price alerts. 0 disables it
    # (alerts then only trigger while someone has the app open).
    alerts_check_seconds: int = Field(default=60, ge=0, le=3600)
    # Optional SMTP for alert emails. Blank host = alerts trigger silently and
    # show up in the UI only.
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    smtp_starttls: bool = Field(default=True)

    # Per-IP rate limits (slowapi syntax: "<count>/<window>")
    rate_limit_research: str = Field(default="30/minute")
    rate_limit_filings: str = Field(default="60/minute")
    rate_limit_auth: str = Field(default="5/minute")
    # SQLite database for research history (sync URI converted to async at runtime).
    database_url: str = Field(default="sqlite+aiosqlite:///./data/verdict.db")
    # Soft request deadline (seconds). LLM calls inside agents have their own timeouts.
    request_timeout_seconds: int = Field(default=120, ge=5, le=600)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]

    @property
    def session_cookie_name(self) -> str:
        # The __Host- prefix is enforced by browsers: Secure, Path=/, no Domain.
        return "__Host-verdict_session" if self.session_cookie_secure else "verdict_session"

    @property
    def resolved_llm_key(self) -> str:
        """Key used for chat/LLM calls.

        Prefers LLM_API_KEY. Falls back to OPENAI_API_KEY only when no custom
        LLM_BASE_URL is set — a non-OpenAI endpoint (e.g. Gemini) needs its own
        key, so we never hand it an ``sk-`` key that can't work there (which
        would surface as a confusing auth error instead of a clear "set a key").
        """
        if self.llm_api_key.strip():
            return self.llm_api_key.strip()
        if not self.llm_base_url.strip():
            return self.openai_api_key.strip()
        return ""

    @property
    def resolved_embedding_key(self) -> str:
        """Key used for embedding calls.

        Prefers EMBEDDING_API_KEY. When EMBEDDING_BASE_URL points at the same
        provider as the chat endpoint (the common one-key Gemini setup), the
        LLM key is reused. Without a custom base URL, falls back to OpenAI.
        """
        if self.embedding_api_key.strip():
            return self.embedding_api_key.strip()
        base = self.embedding_base_url.strip()
        if base:
            if base == self.llm_base_url.strip() and self.llm_api_key.strip():
                return self.llm_api_key.strip()
            return ""
        return self.openai_api_key.strip()

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.environment != "production":
            return self

        problems: list[str] = []
        if not self.session_cookie_secure:
            problems.append("SESSION_COOKIE_SECURE must be true")
        bootstrap = self.auth_bootstrap_token.strip()
        if len(bootstrap) < 32 or bootstrap.lower().startswith(
            ("change", "replace", "generate")
        ):
            problems.append("AUTH_BOOTSTRAP_TOKEN must contain at least 32 characters")
        encryption_key = self.auth_encryption_key.strip()
        try:
            decoded_key = base64.urlsafe_b64decode(encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError, binascii.Error):
            decoded_key = b""
        if len(decoded_key) != 32:
            problems.append("AUTH_ENCRYPTION_KEY must be a valid Fernet key")
        if "*" in self.cors_origins_list:
            problems.append("CORS_ORIGINS cannot contain *")
        if "*" in self.allowed_hosts_list or not self.allowed_hosts_list:
            problems.append("ALLOWED_HOSTS must explicitly list deployment hosts")
        if self.docs_enabled:
            problems.append("DOCS_ENABLED must be false")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
