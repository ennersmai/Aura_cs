# ============================================================================
# Project Panopticon - ADS-B Ingest Service
# ============================================================================

import asyncio
import json
import logging
import os
from typing import Dict, Any, Optional, Set
from datetime import datetime
import structlog
from websockets import connect, WebSocketException
import aiohttp

from config import settings
from services.nats_client import NATSClient
from db.surrealdb_client import SurrealDBClient

log = structlog.get_logger(__name__)


def _load_icao_filter() -> Set[str]:
    """Load military ICAO hex codes from config/icao_filter.json.

    Returns:
        Set of uppercase ICAO hex strings to filter for.
    """
    icao_set: Set[str] = set()

    # Try multiple possible paths for the config file
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "config", "icao_filter.json"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "icao_filter.json"),
        "config/icao_filter.json",
    ]

    for cfg_path in possible_paths:
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r") as f:
                    filter_data = json.load(f)
                codes = filter_data.get("icao_codes", [])
                for code in codes:
                    if isinstance(code, str) and len(code) == 6:
                        icao_set.add(code.upper())
                log.info(
                    f"Loaded {len(icao_set)} military ICAO codes from {cfg_path}"
                )
                return icao_set
            except Exception as e:
                log.warning(f"Failed to load ICAO filter from {cfg_path}: {e}")

    log.warning("No ICAO filter file found; all aircraft will be filtered out")
    return icao_set


# Load military ICAO filter on module import
MILITARY_ICAO_CODES: Set[str] = _load_icao_filter()


class ADSBIngestService:
    """Service for ingesting ADS-B telemetry from public feeds."""

    def __init__(self, nats_client: NATSClient, surreal_client: Optional[SurrealDBClient] = None):
        """Initialize ADS-B ingest service.

        Args:
            nats_client: NATS client for publishing messages
            surreal_client: Optional SurrealDB client for direct data storage
        """
        self.nats_client = nats_client
        self.surreal_client = surreal_client
        self.ws_url = settings.adsb_ws_url
        self.feed_url = settings.adsb_feed_url
        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        """Start the ADS-B ingest service."""
        log.info("Starting ADS-B ingest service")
        self.running = True
        self.session = aiohttp.ClientSession()

        try:
            # Try WebSocket connection first
            await self._connect_websocket()
        except Exception as e:
            log.error(f"WebSocket connection failed, trying HTTP feed: {e}")
            await self._connect_http_feed()

    async def stop(self) -> None:
        """Stop the ADS-B ingest service."""
        log.info("Stopping ADS-B ingest service")
        self.running = False

        if self.session:
            await self.session.close()

    async def _connect_websocket(self) -> None:
        """Connect to ADS-B WebSocket feed."""
        log.info(f"Connecting to ADS-B WebSocket: {self.ws_url}")

        try:
            async with connect(self.ws_url) as websocket:
                log.info("Connected to ADS-B WebSocket")

                while self.running:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=1.0)
                        await self._process_message(message)
                    except asyncio.TimeoutError:
                        continue
                    except WebSocketException as e:
                        log.error(f"WebSocket error: {e}")
                        break
                    except Exception as e:
                        log.error(f"Error processing message: {e}")
                        break

        except Exception as e:
            log.error(f"WebSocket connection failed: {e}")
            raise

    async def _connect_http_feed(self) -> None:
        """Connect to ADS-B HTTP feed (fallback)."""
        if not self.feed_url:
            log.error("No HTTP feed URL configured")
            return

        log.info(f"Connecting to ADS-B HTTP feed: {self.feed_url}")

        try:
            if not self.session:
                log.error("HTTP session not initialized")
                return
            async with self.session.get(self.feed_url) as response:
                log.info("Connected to ADS-B HTTP feed")

                async for line in response.content:
                    if not self.running:
                        break

                    try:
                        message = line.decode("utf-8").strip()
                        await self._process_message(message)
                    except Exception as e:
                        log.error(f"Error processing message: {e}")

        except Exception as e:
            log.error(f"HTTP feed connection failed: {e}")
            raise

    async def _process_message(self, message: str | bytes) -> None:
        """Process a single ADS-B message.

        Args:
            message: Raw message from feed (str or bytes)
        """
        try:
            # Decode bytes to str if needed
            if isinstance(message, bytes):
                message = message.decode("utf-8")

            # Try to parse as JSON
            data = json.loads(message)

            # Validate message structure
            if not self._validate_message(data):
                return

            # Check if military aircraft
            icao_hex = data.get("hex", "").upper()
            if icao_hex in MILITARY_ICAO_CODES:
                log.debug(f"Military aircraft detected: {icao_hex}")
                await self._publish_military_telemetry(data)
            else:
                # Log non-military aircraft
                log.debug(f"Non-military aircraft: {icao_hex}")

        except json.JSONDecodeError:
            # Not JSON, try to parse as line-delimited JSON
            if isinstance(message, str) and message.strip().startswith("{"):
                try:
                    data = json.loads(message)
                    if not self._validate_message(data):
                        return
                    icao_hex = data.get("hex", "").upper()
                    if icao_hex in MILITARY_ICAO_CODES:
                        log.debug(f"Military aircraft detected: {icao_hex}")
                        await self._publish_military_telemetry(data)
                except:
                    pass
        except Exception as e:
            log.error(f"Error processing message: {e}")

    def _validate_message(self, data: Dict[str, Any]) -> bool:
        """Validate ADS-B message structure.

        Args:
            data: Message data

        Returns:
            True if valid, False otherwise
        """
        # Check for required fields
        required_fields = ["hex", "lat", "lon", "alt_baro", "gs", "track", "msg_type"]
        for field in required_fields:
            if field not in data:
                return False

        # Validate numeric fields
        try:
            float(data["lat"])
            float(data["lon"])
            float(data["alt_baro"])
            float(data["gs"])
            float(data["track"])
        except (ValueError, TypeError):
            return False

        return True

    async def _publish_military_telemetry(self, data: Dict[str, Any]) -> None:
        """Publish military telemetry to NATS.

        Args:
            data: Telemetry data
        """
        try:
            # Add timestamp
            data["ingestion_timestamp"] = datetime.utcnow().isoformat()

            # Publish to NATS
            message = json.dumps(data).encode("utf-8")
            await self.nats_client.publish("adsb.mil.telemetry", message)

            log.debug(f"Published military telemetry: {data.get('hex')}")

        except Exception as e:
            log.error(f"Failed to publish military telemetry: {e}")

    async def get_aircraft_count(self) -> int:
        """Get current aircraft count.

        Returns:
            Number of aircraft
        """
        if not self.surreal_client or not self.surreal_client.connected:
            return 0

        try:
            result = await self.surreal_client.query(
                "SELECT count() as total FROM aircraft"
            )
            if result and result[0].result and len(result[0].result) > 0:
                return int(result[0].result[0].get("total", 0))
        except Exception as e:
            log.error(f"Failed to get aircraft count: {e}")
        return 0

    async def get_military_aircraft_count(self) -> int:
        """Get current military aircraft count.

        Returns:
            Number of military aircraft
        """
        if not self.surreal_client or not self.surreal_client.connected:
            return 0

        if not MILITARY_ICAO_CODES:
            return 0

        try:
            icao_list = ", ".join([f'"{code}"' for code in MILITARY_ICAO_CODES])
            query = f'SELECT count() as total FROM aircraft WHERE icao_hex IN [{icao_list}]'
            result = await self.surreal_client.query(query)
            if result and result[0].result and len(result[0].result) > 0:
                return int(result[0].result[0].get("total", 0))
        except Exception as e:
            log.error(f"Failed to get military aircraft count: {e}")
        return 0

    async def get_aircraft_by_region(
        self,
        min_lat: float,
        max_lat: float,
        min_lon: float,
        max_lon: float,
    ) -> list:
        """Get aircraft in a geographic region.

        Args:
            min_lat: Minimum latitude
            max_lat: Maximum latitude
            min_lon: Minimum longitude
            max_lon: Maximum longitude

        Returns:
            List of aircraft in region
        """
        if not self.surreal_client or not self.surreal_client.connected:
            return []

        try:
            polygon = (
                f"POLYGON(({min_lon} {min_lat},{min_lon} {max_lat},"
                f"{max_lon} {max_lat},{max_lon} {min_lat},{min_lon} {min_lat}))"
            )
            query = (
                f'SELECT *, distance::within(coordinates, "{polygon}") as in_region '
                f'FROM aircraft '
                f'WHERE coordinates CONTAINS "{polygon}"'
            )
            result = await self.surreal_client.query(query)
            if result and result[0].result:
                return result[0].result
        except Exception as e:
            log.error(f"Failed to get aircraft by region: {e}")
        return []

    async def get_aircraft_by_type(self, aircraft_type: str) -> list:
        """Get aircraft by type.

        Args:
            aircraft_type: Aircraft type (e.g., "A320", "B737")

        Returns:
            List of aircraft of specified type
        """
        if not self.surreal_client or not self.surreal_client.connected:
            return []

        try:
            result = await self.surreal_client.query(
                'SELECT * FROM aircraft WHERE aircraft_type = $type',
                {"type": aircraft_type}
            )
            if result and result[0].result:
                return result[0].result
        except Exception as e:
            log.error(f"Failed to get aircraft by type: {e}")
        return []