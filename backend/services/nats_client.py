# ============================================================================
# Project Panopticon - NATS Client
# ============================================================================

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional
from nats.aio.client import Client as NATS
from nats.aio.subscription import Subscription
from nats.aio.errors import ErrConnectionClosed, ErrTimeout, ErrNoServers
import structlog

log = structlog.get_logger(__name__)


class NATSClient:
    """Client for NATS message broker operations."""

    def __init__(self, url: str):
        """Initialize NATS client.

        Args:
            url: NATS server URL (e.g., "nats://127.0.0.1:4222")
        """
        self.url = url
        self.client: Optional[NATS] = None
        self.connected = False
        self._subscriptions: Dict[str, Subscription] = {}  # subject -> subscription

    async def connect(self) -> None:
        """Connect to NATS server."""
        try:
            self.client = NATS()
            await self.client.connect(
                servers=[self.url],
                verbose=False,
                allow_reconnect=True,
                max_reconnect_attempts=10,
                reconnect_time_wait=2,
            )
            self.connected = True
            log.info(f"NATS connected to {self.url}")

        except ErrNoServers as e:
            log.error(f"NATS server not found at {self.url}: {e}")
            raise
        except Exception as e:
            log.error(f"Failed to connect to NATS: {e}")
            raise

    async def close(self) -> None:
        """Close NATS connection."""
        if self.client:
            # Unsubscribe from all subscriptions
            for subject, sub in self._subscriptions.items():
                try:
                    await sub.unsubscribe()
                except Exception:
                    pass

            await self.client.close()
            self.connected = False
            log.info("NATS connection closed")

    async def publish(self, subject: str, data: bytes) -> None:
        """Publish a message to a subject.

        Args:
            subject: Message subject
            data: Message data (bytes)
        """
        if not self.client or not self.connected:
            raise RuntimeError("NATS client not connected")

        try:
            await self.client.publish(subject, payload=data)
            log.debug(f"Published to {subject}: {len(data)} bytes")
        except Exception as e:
            log.error(f"Failed to publish to {subject}: {e}")
            raise

    async def subscribe(
        self,
        subject: str,
        callback: Callable[[bytes], Any],
        queue_group: Optional[str] = None,
    ) -> Subscription:
        """Subscribe to a subject.

        Args:
            subject: Message subject
            callback: Async callback function receiving raw bytes
            queue_group: Optional queue group name

        Returns:
            Subscription object
        """
        if not self.client or not self.connected:
            raise RuntimeError("NATS client not connected")

        try:
            async def message_handler(msg):
                """Handle incoming NATS message."""
                try:
                    await callback(msg.data)
                except Exception as e:
                    log.error(f"Error in message handler: {e}")

            sub = await self.client.subscribe(
                subject,
                queue=queue_group or "",
                cb=message_handler,
            )

            self._subscriptions[subject] = sub
            log.info(f"Subscribed to {subject}")
            return sub

        except Exception as e:
            log.error(f"Failed to subscribe to {subject}: {e}")
            raise

    async def unsubscribe(self, subject: str) -> None:
        """Unsubscribe from a subject.

        Args:
            subject: Message subject
        """
        if subject in self._subscriptions:
            sub = self._subscriptions.pop(subject)
            try:
                await sub.unsubscribe()
                log.info(f"Unsubscribed from {subject}")
            except Exception as e:
                log.error(f"Failed to unsubscribe from {subject}: {e}")

    async def request(
        self,
        subject: str,
        data: bytes,
        timeout: float = 1.0,
    ) -> Optional[bytes]:
        """Send a request and wait for a response.

        Args:
            subject: Request subject
            data: Request data (bytes)
            timeout: Request timeout in seconds

        Returns:
            Response data (bytes) or None if timeout
        """
        if not self.client or not self.connected:
            raise RuntimeError("NATS client not connected")

        try:
            msg = await self.client.request(subject, data, timeout=timeout)
            return msg.data
        except ErrTimeout:
            log.warning(f"Request to {subject} timed out")
            return None
        except Exception as e:
            log.error(f"Request to {subject} failed: {e}")
            return None

    async def flush(self) -> None:
        """Flush pending messages."""
        if self.client and self.connected:
            await self.client.flush()
            log.debug("NATS flush completed")

    async def status(self) -> Dict[str, Any]:
        """Get NATS connection status.

        Returns:
            Status information
        """
        if not self.client:
            return {"connected": False}

        return {
            "connected": self.connected,
            "connected_url": self.client.connected_url if self.connected else None,
            "num_subscriptions": len(self._subscriptions),
        }

    async def drain(self) -> None:
        """Drain all subscriptions (close but allow in-flight messages to complete)."""
        if self.client:
            for subject, sub in self._subscriptions.items():
                try:
                    await sub.drain()
                except Exception:
                    pass
            self._subscriptions.clear()
            log.info("NATS subscriptions drained")
