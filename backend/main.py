# ============================================================================
# Project Panopticon - FastAPI Entry Point (Phase 2)
# ============================================================================

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from config import settings
from db.surrealdb_client import SurrealDBClient
from services.nats_client import NATSClient
from services.adsb_ingest import ADSBIngestService
from services.x_scraper import XScraperService

# Routers
from routers.events import router as events_router
from routers.aircraft import router as aircraft_router
from routers.ai import router as ai_router
from routers.sources import router as sources_router

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger(__name__)

# Global clients
surreal_client: Optional[SurrealDBClient] = None
nats_client: Optional[NATSClient] = None
adsb_service: Optional[ADSBIngestService] = None
x_scraper_service: Optional[XScraperService] = None

# WebSocket connections pool for broadcasting
websocket_connections: Set[WebSocket] = set()

# Background task references
_bg_tasks: List[asyncio.Task] = []


# ============================================================================
# Schema Initialization
# ============================================================================

async def _init_surreal_schema(client: SurrealDBClient) -> None:
    """Apply SurrealDB schema from scripts/init_schema.surql."""
    schema_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "scripts",
        "init_schema.surql",
    )

    if not os.path.exists(schema_path):
        log.warning(f"Schema file not found at {schema_path}, skipping schema init")
        return

    try:
        with open(schema_path, "r") as f:
            schema_sql = f.read()

        # Split by statement and execute each
        statements = _split_surql_statements(schema_sql)
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt:
                continue
            try:
                await client.query(stmt)
                log.debug(f"Executed: {stmt[:80]}...")
            except Exception as e:
                # Schema statements may fail if objects already exist (idempotent)
                log.debug(f"Statement skipped (may already exist): {str(e)[:80]}")

        log.info("SurrealDB schema initialized successfully")

    except Exception as e:
        log.error(f"Failed to initialize SurrealDB schema: {e}")
        raise


def _split_surql_statements(schema_sql: str) -> List[str]:
    """Split SurrealQL into individual statements, skipping comments and blanks."""
    lines = schema_sql.split("\n")
    statements: List[str] = []
    current: List[str] = []

    for line in lines:
        stripped = line.strip()

        # Skip comments and empty lines
        if stripped.startswith("//") or stripped == "":
            continue

        current.append(line)

        # Semicolon or end of a block means end of statement
        if stripped.endswith(";") and not stripped.startswith("DEFINE TABLE") and not stripped.startswith("DEFINE FIELD"):
            if current:
                statements.append("\n".join(current))
                current = []

    # Any remaining content
    if current:
        statements.append("\n".join(current))

    return statements


# ============================================================================
# Lifespan (App Lifecycle)
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events."""
    global surreal_client, nats_client, adsb_service, x_scraper_service, _bg_tasks

    # Startup
    log.info("Starting Project Panopticon Phase 2 backend...")

    # --- Initialize SurrealDB ---
    surreal_client = SurrealDBClient(
        url=settings.surreal_url,
        namespace=settings.surreal_ns,
        database=settings.surreal_db,
        user=settings.surreal_user,
        password=settings.surreal_pass,
    )

    try:
        await surreal_client.connect()
        log.info("SurrealDB connected successfully")

        # Apply schema
        await _init_surreal_schema(surreal_client)

    except Exception as e:
        log.error(f"Failed to connect to SurrealDB: {e}")
        raise

    # --- Initialize NATS ---
    nats_client = NATSClient(url=settings.nats_url)
    try:
        await nats_client.connect()
        log.info("NATS connected successfully")

        # Subscribe to all sensor edge subjects
        await nats_client.subscribe("adsb.mil.telemetry", handle_adsb_message)
        log.info("Subscribed to adsb.mil.telemetry")

        await nats_client.subscribe("osint.x.raw", handle_x_message)
        log.info("Subscribed to osint.x.raw")

    except Exception as e:
        log.error(f"Failed to connect to NATS: {e}")
        raise

    # --- Start Sensor Edge Services ---
    adsb_service = ADSBIngestService(nats_client=nats_client, surreal_client=surreal_client)
    x_scraper_service = XScraperService(nats_client=nats_client, surreal_client=surreal_client)

    # Start ADS-B as background task
    _bg_tasks.append(asyncio.create_task(_safe_run_adsb(adsb_service)))

    # Start X scraper as background task (only if auth tokens configured)
    if settings.x_auth_token and settings.x_csrf_token:
        _bg_tasks.append(asyncio.create_task(_safe_run_x_scraper(x_scraper_service)))
    else:
        log.warning("X/Twitter auth tokens not configured - scraper not started")

    log.info("All sensor edge services started")

    yield

    # Shutdown
    log.info("Shutting down Project Panopticon backend...")

    # Cancel background tasks
    for task in _bg_tasks:
        if not task.done():
            task.cancel()
    _bg_tasks.clear()

    # Stop sensor services
    if adsb_service:
        await adsb_service.stop()
    if x_scraper_service:
        await x_scraper_service.stop()

    # Close WebSocket connections
    for ws in list(websocket_connections):
        try:
            await ws.close()
        except:
            pass
    websocket_connections.clear()

    # Close database and message broker
    if surreal_client:
        await surreal_client.close()
        log.info("SurrealDB connection closed")

    if nats_client:
        await nats_client.close()
        log.info("NATS connection closed")


async def _safe_run_adsb(service: ADSBIngestService) -> None:
    """Run ADS-B service, logging any errors."""
    try:
        await service.start()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.error(f"ADS-B ingest service crashed: {e}", exc_info=True)


async def _safe_run_x_scraper(service: XScraperService) -> None:
    """Run X scraper service, logging any errors."""
    try:
        await service.start()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log.error(f"X/Twitter scraper service crashed: {e}", exc_info=True)


# Create FastAPI app
app = FastAPI(
    title="Project Panopticon API",
    description="OSINT geospatial aggregator and sensor fusion engine (Phase 3)",
    version="3.0.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(events_router)
app.include_router(aircraft_router)
app.include_router(ai_router)
app.include_router(sources_router)


# ============================================================================
# WebSocket Management
# ============================================================================

async def _broadcast(data: Dict[str, Any]) -> None:
    """Broadcast JSON data to all connected WebSocket clients."""
    message = json.dumps(data)
    disconnected: Set[WebSocket] = set()

    for ws in websocket_connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)

    # Clean up disconnected clients
    for ws in disconnected:
        websocket_connections.discard(ws)


# ============================================================================
# Health Check Endpoint
# ============================================================================
@app.get("/api/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint with component status."""
    status = {
        "status": "ok",
        "version": "3.0.0",
        "components": {
            "surrealdb": "unknown",
            "nats": "unknown",
            "adsb_service": "unknown",
            "x_scraper_service": "unknown",
        },
        "websocket_clients": len(websocket_connections),
        "uptime": datetime.utcnow().isoformat(),
    }

    if surreal_client:
        try:
            await surreal_client.query("SELECT * FROM information.schema LIMIT 1")
            status["components"]["surrealdb"] = "connected"
        except Exception as e:
            status["components"]["surrealdb"] = f"error: {str(e)}"

    if nats_client:
        try:
            await nats_client.publish("health.check", b"ping")
            status["components"]["nats"] = "connected"
        except Exception as e:
            status["components"]["nats"] = f"error: {str(e)}"

    status["components"]["adsb_service"] = "running" if adsb_service and adsb_service.running else "stopped"
    status["components"]["x_scraper_service"] = "running" if x_scraper_service and x_scraper_service.running else "stopped"

    return status


# ============================================================================
# WebSocket Endpoint
# ============================================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time data streaming to the 3D frontend."""
    await websocket.accept()
    websocket_connections.add(websocket)
    log.info(f"WebSocket client connected (total: {len(websocket_connections)})")

    try:
        # Send welcome message
        await websocket.send_text(json.dumps({
            "type": "connected",
            "message": "Connected to Project Panopticon",
            "active_layers": ["ADS-B_Military", "X_Scraper_Alerts"],
            "timestamp": datetime.utcnow().isoformat(),
        }))

        # Keep connection alive and handle client messages
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                action = msg.get("action", "")

                if action == "subscribe_layers":
                    # Client wants specific data layers
                    layers = msg.get("layers", [])
                    log.info(f"Client subscribed to layers: {layers}")
                    await websocket.send_text(json.dumps({
                        "type": "layer_subscription",
                        "layers": layers,
                    }))

                elif action == "camera.move":
                    # Client camera moved - could trigger server-side region queries
                    pass

                elif action == "entity.select":
                    # Client selected an entity
                    entity_id = msg.get("entity_id")
                    if entity_id and surreal_client:
                        try:
                            result = await surreal_client.select("aircraft", entity_id)
                            await websocket.send_text(json.dumps({
                                "type": "entity_detail",
                                "entity_id": entity_id,
                                "data": result,
                            }))
                        except Exception as e:
                            log.error(f"Entity query failed: {e}")

            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        log.info("WebSocket client disconnected")
    except Exception as e:
        log.error(f"WebSocket error: {e}")
    finally:
        websocket_connections.discard(websocket)
        log.info(f"WebSocket client removed (total: {len(websocket_connections)})")


# ============================================================================
# NATS Message Handlers
# ============================================================================
async def handle_adsb_message(msg: bytes) -> None:
    """Handle incoming ADS-B telemetry from NATS - store in DB and broadcast to clients."""
    try:
        data = json.loads(msg.decode("utf-8"))

        if surreal_client:
            try:
                # Store aircraft telemetry in SurrealDB
                aircraft_record = {
                    "icao_hex": data.get("hex", "").upper(),
                    "callsign": data.get("flight", data.get("callsign", "")),
                    "coordinates": {
                        "type": "Point",
                        "coordinates": [float(data.get("lon", 0)), float(data.get("lat", 0))],
                    },
                    "altitude": float(data.get("alt_baro", 0)),
                    "velocity": float(data.get("gs", 0)),
                    "heading": float(data.get("track", 0)),
                    "aircraft_type": data.get("t", ""),
                    "last_seen": datetime.utcnow().isoformat(),
                }

                # Upsert by ICAO hex
                existing = await surreal_client.select("aircraft")
                existing_icaos = [r.get("icao_hex") if isinstance(r, dict) else getattr(r, "icao_hex", None) for r in existing]

                if aircraft_record["icao_hex"] in existing_icaos:
                    await surreal_client.query(
                        "UPDATE aircraft SET coordinates = $coords, altitude = $alt, velocity = $vel, heading = $hdg, last_seen = $ts WHERE icao_hex = $icao",
                        {
                            "icao": aircraft_record["icao_hex"],
                            "coords": {"type": "Point", "coordinates": [aircraft_record["coordinates"]["coordinates"][0], aircraft_record["coordinates"]["coordinates"][1]]},
                            "alt": aircraft_record["altitude"],
                            "vel": aircraft_record["velocity"],
                            "hdg": aircraft_record["heading"],
                            "ts": aircraft_record["last_seen"],
                        },
                    )
                else:
                    await surreal_client.create("aircraft", aircraft_record)

                log.debug(f"Stored aircraft: {aircraft_record['icao_hex']}")

            except Exception as e:
                log.error(f"Failed to store aircraft in SurrealDB: {e}")

        # Broadcast to WebSocket clients
        await _broadcast({
            "type": "adsb_telemetry",
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })

    except Exception as e:
        log.error(f"Error processing ADS-B message: {e}")


async def handle_x_message(msg: bytes) -> None:
    """Handle incoming X/Twitter data from NATS - store in DB and broadcast to clients."""
    try:
        data = json.loads(msg.decode("utf-8"))

        if surreal_client:
            try:
                # Store event in SurrealDB
                event_record = {
                    "title": data.get("title", data.get("text", ""))[:200],
                    "description": data.get("text", data.get("description", "")),
                    "event_type": "social_media",
                    "severity": data.get("severity", "medium"),
                    "source": "x_twitter",
                    "timestamp": data.get("timestamp", datetime.utcnow().isoformat()),
                    "raw_data": data,
                }

                # Add coordinates if available
                if "lat" in data and "lon" in data:
                    event_record["coordinates"] = {
                        "type": "Point",
                        "coordinates": [float(data["lon"]), float(data["lat"])],
                    }

                await surreal_client.create("event", event_record)
                log.debug(f"Stored event: {event_record['title'][:50]}")

            except Exception as e:
                log.error(f"Failed to store event in SurrealDB: {e}")

        # Broadcast to WebSocket clients
        await _broadcast({
            "type": "x_alert",
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        })

    except Exception as e:
        log.error(f"Error processing X/Twitter message: {e}")


# ============================================================================
# API Routes are now in separate router modules:
#   routers/events.py  - /api/events*
#   routers/aircraft.py - /api/aircraft*
#   routers/ai.py      - /api/ai/*
#   routers/sources.py - /api/sources
# ============================================================================


# ============================================================================
# Error Handlers
# ============================================================================
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    log.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc) if settings.debug else None},
    )


# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )