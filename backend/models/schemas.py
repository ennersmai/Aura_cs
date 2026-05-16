# ============================================================================
# Project Panopticon - Pydantic Data Models
# ============================================================================

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---- Aircraft Models ----

class AircraftCoordinate(BaseModel):
    """GeoJSON Point coordinate for aircraft position."""
    type: str = "Point"
    coordinates: List[float]  # [lon, lat]


class AircraftBase(BaseModel):
    """Base aircraft entity fields."""
    icao_hex: str = Field(..., min_length=6, max_length=6, description="ICAO 24-bit hex code")
    callsign: Optional[str] = None
    coordinates: AircraftCoordinate
    altitude: Optional[float] = None  # feet
    velocity: Optional[float] = None  # knots
    heading: Optional[float] = None  # degrees
    aircraft_type: Optional[str] = None
    owner_entity: Optional[str] = None  # record<entity> reference


class AircraftCreate(AircraftBase):
    """Payload for creating a new aircraft record."""
    last_seen: Optional[datetime] = Field(default_factory=datetime.utcnow)


class AircraftUpdate(BaseModel):
    """Payload for updating an existing aircraft."""
    callsign: Optional[str] = None
    coordinates: Optional[AircraftCoordinate] = None
    altitude: Optional[float] = None
    velocity: Optional[float] = None
    heading: Optional[float] = None
    aircraft_type: Optional[str] = None
    last_seen: Optional[datetime] = None


class AircraftResponse(AircraftBase):
    """Aircraft record returned from the database."""
    id: str
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Event Models ----

class EventCoordinate(BaseModel):
    """GeoJSON Point coordinate for event location."""
    type: str = "Point"
    coordinates: List[float]  # [lon, lat]


class EventBase(BaseModel):
    """Base event entity fields."""
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    coordinates: Optional[EventCoordinate] = None
    event_type: str = "social_media"
    severity: Optional[str] = "medium"  # low, medium, high, critical
    source: Optional[str] = None
    timestamp: Optional[datetime] = None


class EventCreate(EventBase):
    """Payload for creating a new event record."""
    raw_data: Optional[Dict[str, Any]] = None


class EventUpdate(BaseModel):
    """Payload for updating an existing event."""
    title: Optional[str] = None
    description: Optional[str] = None
    coordinates: Optional[EventCoordinate] = None
    severity: Optional[str] = None
    timestamp: Optional[datetime] = None


class EventResponse(EventBase):
    """Event record returned from the database."""
    id: str
    raw_data: Optional[Dict[str, Any]] = None
    embedding: Optional[List[float]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Entity Models (Organizations, Individuals) ----

class EntityBase(BaseModel):
    """Base entity fields."""
    name: str = Field(..., max_length=200)
    entity_type: str  # organization, individual, government, military
    aliases: Optional[List[str]] = None
    coordinates: Optional[EventCoordinate] = None
    description: Optional[str] = None
    website: Optional[str] = None
    social_media: Optional[List[str]] = None


class EntityCreate(EntityBase):
    """Payload for creating a new entity."""
    pass


class EntityResponse(EntityBase):
    """Entity record returned from the database."""
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---- Health & Status Models ----

class ComponentStatus(BaseModel):
    """Individual component health status."""
    surrealdb: str = "unknown"
    nats: str = "unknown"
    adsb_service: str = "unknown"
    x_scraper_service: str = "unknown"


class HealthResponse(BaseModel):
    """Health check endpoint response."""
    status: str = "ok"
    version: str = "2.0.0"
    components: ComponentStatus
    websocket_clients: int = 0
    uptime: Optional[str] = None


# ---- AI Query Models ----

class AIQueryRequest(BaseModel):
    """AI query request payload."""
    query: str = Field(..., min_length=1, max_length=1000)
    viewport: Optional[Dict[str, float]] = Field(
        default_factory=lambda: {"lat": 44.0, "lon": 31.0, "height": 20000000}
    )
    active_layers: List[str] = Field(default_factory=list)


class AIAction(BaseModel):
    """Structured action returned by AI."""
    action: str
    entity_id: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    height: Optional[float] = None
    query: Optional[str] = None
    icao_hex: Optional[str] = None
    message: Optional[str] = None


class AIQueryResponse(BaseModel):
    """AI query response."""
    success: bool
    action: AIAction
    raw_response: Optional[str] = None


class AIModel(BaseModel):
    """OpenRouter model descriptor."""
    id: str
    name: str


# ---- Data Source Models ----

class DataSourceStatus(BaseModel):
    """Individual data source status."""
    service: str
    status: str
    url: Optional[str] = None
    nats_subject: Optional[str] = None
    configured: Optional[bool] = None  # for services that need API keys


class SourcesResponse(BaseModel):
    """Data sources status dashboard response."""
    adsb: DataSourceStatus
    x_twitter: DataSourceStatus
    ai_orchestrator: DataSourceStatus
    tavily: DataSourceStatus


# ---- WebSocket Message Models ----

class WebSocketMessage(BaseModel):
    """Generic WebSocket message envelope."""
    type: str
    data: Optional[Any] = None
    timestamp: str


class AdsbTelemetry(BaseModel):
    """ADS-B telemetry data as received from feed."""
    hex: str
    flight: Optional[str] = None
    lat: float
    lon: float
    alt_baro: Optional[float] = None
    gs: Optional[float] = None
    track: Optional[float] = None
    t: Optional[str] = None
    msg_type: Optional[str] = None


class XAlertData(BaseModel):
    """X/Twitter alert data."""
    id: Optional[str] = None
    text: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    hashtags: List[str] = Field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    created_at: Optional[str] = None
    source: str = "x_twitter_cdp"


# ---- Pagination Models ----

class PaginationParams(BaseModel):
    """Common pagination parameters."""
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class RegionQueryParams(PaginationParams):
    """Geospatial region query parameters."""
    min_lat: float = Field(..., ge=-90, le=90)
    max_lat: float = Field(..., ge=-90, le=90)
    min_lon: float = Field(..., ge=-180, le=180)
    max_lon: float = Field(..., ge=-180, le=180)


# ---- Error Response Model ----

class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
    error: Optional[str] = None
