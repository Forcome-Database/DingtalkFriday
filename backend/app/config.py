"""
Application configuration using pydantic-settings.
Reads environment variables from .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # DingTalk API configuration
    dingtalk_app_key: str = ""
    dingtalk_app_secret: str = ""
    dingtalk_base_url: str = "https://oapi.dingtalk.com"

    # Database configuration
    database_url: str = "sqlite+aiosqlite:///./data/leave.db"

    # Root department ID (top-level org to sync and display)
    root_dept_id: int = 55205497

    # Comma-separated leave type names to display (empty = show all)
    leave_type_names: str = ""

    # Admin user ID for API calls that require operator identity
    admin_userid: str = ""

    # Auth & admin configuration
    admin_phones: str = ""  # Comma-separated admin phone numbers
    jwt_secret: str = "change-me-in-production"
    jwt_expire_hours: int = 24

    # Scheduled sync cron expression (empty = disabled), e.g. "0 2 * * *"
    sync_cron: str = ""

    # DingTalk Corp ID (required for H5 micro-app login)
    dingtalk_corp_id: str = ""


# Singleton settings instance
settings = Settings()
