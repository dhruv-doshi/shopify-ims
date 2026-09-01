from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    telegram_allowed_user_id: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_vision_model: str = "google/gemini-2.5-flash"
    openrouter_image_model: str = "google/gemini-2.5-flash-image"
    app_public_url: str = "http://127.0.0.1:8000"
    link_ttl_minutes: int = 60
    link_ttl_hours: int = 0  # legacy fallback when link_ttl_minutes is 0
    photo_batch_idle_seconds: int = 3
    image_concurrency: int = 3
    shopify_store_domain: str = ""
    shopify_client_id: str = ""
    shopify_client_secret: str = ""
    shopify_admin_access_token: str = ""  # optional legacy static token (shpat_)
    shopify_api_version: str = "2025-01"
    database_url: str = "sqlite+aiosqlite:///./data/app.db"
    upload_dir: str = "data/uploads"

    @property
    def shopify_configured(self) -> bool:
        if not self.shopify_store_domain:
            return False
        if self.shopify_admin_access_token:
            return True
        return bool(self.shopify_client_id and self.shopify_client_secret)

    def is_user_allowed(self, user_id: int) -> bool:
        if not self.telegram_allowed_user_id:
            return True
        return str(user_id) == self.telegram_allowed_user_id


@lru_cache
def get_settings() -> Settings:
    return Settings()
