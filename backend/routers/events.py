# ============================================================================
# Project Panopticon - Events API Router
# ============================================================================

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
import structlog

from db.surrealdb_client import SurrealDBClient

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/events", tags=["events"])


def _get_surreal() -> SurrealDBClient:
    """Get SurrealDB client from app state (set by main.py)."""
    from main import surreal_client
    if not surreal_client:
        raise HTTPException(status_code=503, detail="Database not connected")
    return surreal_client


@router.get("")
async def get_events(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get paginated events with optional type/severity filters."""
    client = _get_surreal()

    try:
        query = "SELECT * FROM event"
        conditions = []

        if event_type:
            conditions.append(f"event_type = '{event_type}'")
        if severity:
            conditions.append(f"severity = '{severity}'")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY timestamp DESC LIMIT {limit} START {offset}"

        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to query events: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/region")
async def get_events_in_region(
    min_lat: float = Query(..., ge=-90, le=90),
    max_lat: float = Query(..., ge=-90, le=90),
    min_lon: float = Query(..., ge=-180, le=180),
    max_lon: float = Query(..., ge=-180, le=180),
    limit: int = Query(default=100, ge=1, le=1000),
) -> List[Dict[str, Any]]:
    """Get events within a geographic bounding box."""
    client = _get_surreal()

    try:
        query = f"""
        SELECT * FROM event
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
        ORDER BY timestamp DESC
        LIMIT {limit}
        """
        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to query events in region: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{event_id}")
async def get_event_by_id(event_id: str) -> Dict[str, Any]:
    """Get a specific event by its ID."""
    client = _get_surreal()

    try:
        query = f"SELECT * FROM event WHERE id = '{event_id}'"
        result = await client.query(query)
        if not result:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
        return result[0] if isinstance(result, list) else result
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"Failed to query event {event_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/nearest")
async def search_nearest_events(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius_km: float = Query(default=100, ge=1, le=10000),
    limit: int = Query(default=20, ge=1, le=100),
) -> List[Dict[str, Any]]:
    """Vector search: find events nearest to a point within radius."""
    client = _get_surreal()

    try:
        query = f"""
        SELECT *, geo::distance(coordinates, point({lon}, {lat})) AS distance
        FROM event
        WHERE geo::distance(coordinates, point({lon}, {lat})) <= {radius_km * 1000}
        ORDER BY distance ASC
        LIMIT {limit}
        """
        result = await client.query(query)
        return result
    except Exception as e:
        log.error(f"Failed to search nearest events: {e}")
        raise HTTPException(status_code=500, detail=str(e))
