# ============================================================================
# Project Panopticon - Sources API Router
# ============================================================================

from typing import Any, Dict

from fastapi import APIRouter
import structlog

from config import settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def get_data_sources() -> Dict[str, Any]:
    """Get status of all data sources."""
    from main import adsb_service, x_scraper_service

    return {
        "adsb": {
            "service": "ADS-B Telemetry",
            "url": settings.adsb_ws_url,
            "status": "running" if adsb_service and adsb_service.running else "stopped",
            "nats_subject": "adsb.mil.telemetry",
            "filter_type": "military_icao",
        },
        "x_twitter": {
            "service": "X/Twitter Scraper",
            "status": "running" if x_scraper_service and x_scraper_service.running else "stopped",
            "nats_subject": "osint.x.raw",
            "authenticated": bool(settings.x_auth_token or settings.x_api_key),
        },
        "ai_orchestrator": {
            "service": "OpenRouter API",
            "model": settings.openrouter_model,
            "configured": bool(settings.openrouter_api_key),
        },
        "tavily": {
            "service": "Tavily Search",
            "configured": bool(settings.tavily_api_key),
        },
        "nats": {
            "service": "NATS Message Broker",
            "url": settings.nats_url,
        },
        "surrealdb": {
            "service": "SurrealDB",
            "url": settings.surreal_url,
            "namespace": settings.surreal_ns,
            "database": settings.surreal_db,
        },
    }
