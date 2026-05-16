# ============================================================================
# Project Panopticon - Aircraft API Router
# ============================================================================

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
import structlog

from db.surrealdb_client import SurrealDBClient

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/aircraft", tags=["aircraft"])


def _get_surreal() -> SurrealDBClient:
    """Get SurrealDB client from app state."""
    from main import surreal_client
    if not surreal_client:
        raise HTTPException(status_code=503, detail="Database not connected")
    return surreal_client


@router.get("")
async def get_aircraft(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    aircraft_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get paginated aircraft list with optional type filter."""
    client = _get_surreal()

    try:
        query = "SELECT * FROM aircraft"
        if aircraft_type:
            query += f" WHERE aircraft_type = '{aircraft_type}'"
        query += f" ORDER BY last_seen DESC LIMIT {limit} START {offset}"

        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to query aircraft: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/region")
async def get_aircraft_in_region(
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    limit: int = Query(default=100, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """Get aircraft within a geographic bounding box."""
    client = _get_surreal()

    try:
        query = f"""
        SELECT * FROM aircraft
        WHERE coordinates INSIDE {{
            type: 'Polygon',
            coordinates: [[
                [{min_lon}, {min_lat}],
                [{max_lon}, {min_lat}],
                [{max_lon}, {max_lat}],
                [{min_lon}, {max_lat}],
                [{min_lon}, {min_lat}]
            ]]
        }}
        ORDER BY last_seen DESC
        LIMIT {limit}
        """
        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to query aircraft in region: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{icao_hex}")
async def get_aircraft_by_icao(icao_hex: str) -> Dict[str, Any]:
    """Get a specific aircraft by its ICAO hex code."""
    client = _get_surreal()

    try:
        query = f"SELECT * FROM aircraft WHERE icao_hex = '{icao_hex.upper()}'"
        result = await client.query(query)
        if not result:
            raise HTTPException(status_code=404, detail=f"Aircraft {icao_hex} not found")
        return result[0] if isinstance(result, list) else result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to query aircraft {icao_hex}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/active")
async def get_active_aircraft(
    since_minutes: int = Query(default=5, ge=1, le=60),
    limit: int = Query(default=100, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """Get aircraft recently seen (active in last N minutes)."""
    client = _get_surreal()

    try:
        query = f"""
        SELECT * FROM aircraft
        WHERE last_seen >= time::now() - {since_minutes}m
        ORDER BY last_seen DESC
        LIMIT {limit}
        """
        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to query active aircraft: {e}")
        raise HTTPException(status_code=500, detail=str(e))
