from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str | None = None
    SUPABASE_JWT_SECRET: str | None = None
    # Server-side only - never sent to Web/Mobile clients. Used to fetch bill
    # images from Supabase Storage for the OCR pipeline (Backend Block 8).
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    # design.md SS1: Google Cloud Vision (OCR) + Gemini (OCR-text -> taxonomy
    # classification). Both optional at the settings level so the app can
    # still boot and everything else keep working before these are set up -
    # only Backend Block 8's pipeline actually needs them.
    GOOGLE_APPLICATION_CREDENTIALS: str | None = None
    GEMINI_API_KEY: str | None = None
    ENV: str = "dev"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()  # type: ignore[call-arg]  # required fields load from the environment
