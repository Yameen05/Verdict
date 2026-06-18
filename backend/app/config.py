from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", description="OpenAI API key")

    pinecone_api_key: str = Field(default="", description="Pinecone API key")
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

    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dim: int = Field(default=1536)
    llm_model: str = Field(default="gpt-4o-mini")

    # --- LLM provider routing (OpenAI-compatible endpoints) ---
    # Leave blank to call api.openai.com. To use a different provider that
    # speaks the OpenAI API, set its base URL here and point LLM_MODEL at one of
    # that provider's models. Examples:
    #   Google Gemini : https://generativelanguage.googleapis.com/v1beta/openai/   (model: gemini-2.0-flash)
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
    log_level: str = Field(default="INFO")
    # If set, requests must carry header X-API-Key: <value>. Empty = open.
    verdict_api_key: str = Field(default="")
    # Per-IP rate limits (slowapi syntax: "<count>/<window>")
    rate_limit_research: str = Field(default="30/minute")
    rate_limit_filings: str = Field(default="60/minute")
    # SQLite database for research history (sync URI converted to async at runtime).
    database_url: str = Field(default="sqlite+aiosqlite:///./data/verdict.db")
    # Soft request deadline (seconds). LLM calls inside agents have their own timeouts.
    request_timeout_seconds: int = Field(default=120, ge=5, le=600)

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
