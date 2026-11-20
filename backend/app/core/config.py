from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str | None = None
    # Legacy shared-secret (HS256) JWT verification. Optional: projects on
    # Supabase's newer asymmetric signing keys (ES256/RS256) are verified
    # against the project's public JWKS endpoint instead (see
    # app/core/security.py), which only needs SUPABASE_URL.
    SUPABASE_JWT_SECRET: str | None = None
    # Server-side only - never sent to Web/Mobile clients. Used to fetch bill
    # images from Supabase Storage for the OCR pipeline, and to mint
    # short-lived signed URLs so group members can view a bill's receipt.
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    # Receipt OCR + OCR-text -> taxonomy classification both run on the
    # Claude API (decision 2026-11-20, superseding design.md SS1's Google
    # Cloud Vision + Gemini). Optional at the settings level so the app still
    # boots without it - a bill uploaded while it's unset simply falls back
    # to needs_manual_entry (design.md SS13).
    ANTHROPIC_API_KEY: str | None = None
    CLAUDE_MODEL: str = "claude-haiku-5-5"
    # Comma-separated list of browser origins allowed to call this API
    # (e.g. "https://billsplit.vercel.app,http://localhost:3000").
    CORS_ORIGINS: str = "http://localhost:3000"
    # Optional regex for extra allowed origins - handy for Vercel preview
    # deployments, e.g. r"https://billsplit-.*\.vercel\.app".
    CORS_ORIGIN_REGEX: str | None = None
    ENV: str = "dev"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Supabase's dashboard hands out "postgres://..." connection strings;
        # SQLAlchemy 2.x only recognizes the "postgresql://" scheme.
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://") :]
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip().rstrip("/") for origin in self.CORS_ORIGINS.split(",") if origin.strip()
        ]


settings = Settings()  # type: ignore[call-arg]  # required fields load from the environment
