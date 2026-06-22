"""Application settings via pydantic-settings / environment variables.

Every field has a sensible local-dev default so the app boots with no env file.
Field names are UPPER_CASE and env-overridable (case-insensitive). The
module-level ``settings`` singleton is imported across the backend.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- Build artifacts (local paths; the offline pipeline writes here) ---
    INDEX_DIR: str = "build/output/indexes"
    RECORDS_PATH: str = "build/output/records.json"
    METADATA_PATH: str = "build/output/metadata.json"

    # --- R2 (download-if-missing at startup; empty = local-only) ---
    R2_INDEX_BASE_URL: str = ""
    R2_DOC_BASE_URL: str = ""

    # --- Analytics store (sqlite locally, postgres on Railway) ---
    DATABASE_URL: str = "sqlite:///./events.db"

    # --- Auth: "tok:Display Name,tok2:Name2" ---
    ACCESS_TOKENS: str = "demo:Demo User"

    # --- Embeddings: none|arctic|openai. v1 serves BM25-only ("none"). ---
    EMBED_BACKEND: str = "none"
    OPENAI_API_KEY: str = ""

    # --- Runtime ---
    ENV: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
