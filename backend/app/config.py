"""
Application configuration using pydantic-settings.
Reads environment variables from .env file.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
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


# Singleton settings instance
settings = Settings()
