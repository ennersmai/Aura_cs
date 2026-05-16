# ============================================================================
# Project Panopticon - Configuration Loader
# ============================================================================

import os
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # OpenRouter AI
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")

    # Tavily Search
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # SurrealDB
    surreal_url: str = os.getenv("SURREAL_URL", "ws://127.0.0.1:8000/rpc")
    surreal_ns: str = os.getenv("SURREAL_NS", "panopticon")
    surreal_db: str = os.getenv("SURREAL_DB", "osint")
    surreal_user: str = os.getenv("SURREAL_USER", "root")
    surreal_pass: str = os.getenv("SURREAL_PASS", "root")

    # NATS
    nats_url: str = os.getenv("NATS_URL", "nats://127.0.0.1:4222")

    # ADS-B
    adsb_ws_url: str = os.getenv("ADSB_WS_URL", "wss://api.adsb.lol/api/ws")
    adsb_feed_url: Optional[str] = os.getenv("ADSB_FEED_URL")

    # X/Twitter (Phase 2)
    x_auth_token: str = os.getenv("X_AUTH_TOKEN", "")
    x_csrf_token: str = os.getenv("X_CSRF_TOKEN", "")
    x_api_key: str = os.getenv("X_API_KEY", "")
    x_api_secret: str = os.getenv("X_API_SECRET", "")
    x_access_token: str = os.getenv("X_ACCESS_TOKEN", "")
    x_access_secret: str = os.getenv("X_ACCESS_SECRET", "")

    # Cesium Ion
    cesium_ion_access_token: str = os.getenv("CESIUM_ION_ACCESS_TOKEN", "")

    # Server
    api_host: str = os.getenv("API_HOST", "127.0.0.1")
    api_port: int = int(os.getenv("API_PORT", "8080"))
    vite_port: int = int(os.getenv("VITE_PORT", "5173"))

    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings