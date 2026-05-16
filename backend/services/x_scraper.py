# ============================================================================
# Project Panopticon - X/Twitter CDP Scraper Service (Phase 2)
# ============================================================================

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import structlog
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from config import settings
from services.nats_client import NATSClient
from db.surrealdb_client import SurrealDBClient

log = structlog.get_logger(__name__)


class XScraperService:
    """Service for scraping X/Twitter data using CDP headless browser.

    Connects to X/Twitter via Playwright (Chromium). Intercepts GraphQL XHR
    responses, extracts tweets/events, and publishes to NATS subject 'osint.x.raw'.
    """

    # X/Twitter GraphQL endpoint patterns to intercept
    GRAPHQL_PATTERNS = [
        "/i/api/graphql/",  # Main GraphQL API
        "/api/1.1/",        # REST API (fallback)
    ]

    def __init__(
        self,
        nats_client: NATSClient,
        surreal_client: Optional[SurrealDBClient] = None,
    ):
        """Initialize X/Twitter scraper service.

        Args:
            nats_client: NATS client for publishing messages
            surreal_client: Optional SurrealDB client for direct data storage
        """
        self.nats_client = nats_client
        self.surreal_client = surreal_client
        self.running = False
        self.captured_tweets: List[Dict[str, Any]] = []
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    # ---- Authentication ----
    def _has_auth(self) -> bool:
        """Check if X/Twitter authentication is fully configured."""
        return bool(
            settings.x_auth_token
            or settings.x_api_key
        )

    # ---- Lifecycle ----
    async def start(self) -> None:
        """Start the X/Twitter scraper service."""
        log.info("Starting X/Twitter CDP scraper service...")

        if not self._has_auth():
            log.warning(
                "X/Twitter auth tokens not configured. "
                "Scraper will run in unauthenticated mode (limited data)."
            )

        self.running = True

        try:
            async with async_playwright() as p:
                self._playwright = p

                # Launch browser with CDP remote debugging
                self._browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        "--remote-debugging-port=0",  # auto-assign
                        "--remote-allow-origins=*",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-sandbox",
                    ],
                )

                self._context = await self._browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1920, "height": 1080},
                )
                self._page = await self._context.new_page()

                # Set auth cookies if available
                if settings.x_auth_token:
                    await self._set_auth_cookies()

                # Install XHR interception
                await self._install_interceptor()

                log.info("X/Twitter scraper browser launched")
                await self._scrape_loop()

        except asyncio.CancelledError:
            log.info("X/Twitter scraper cancelled")
        except Exception as e:
            log.error(f"X/Twitter scraper crashed: {e}", exc_info=True)
        finally:
            await self._cleanup_browser()

    async def stop(self) -> None:
        """Stop the X/Twitter scraper service."""
        log.info("Stopping X/Twitter scraper service...")
        self.running = False
        await self._cleanup_browser()

    async def _cleanup_browser(self) -> None:
        """Safely close browser resources."""
        for resource in [self._page, self._context, self._browser]:
            attr = resource
            if attr is not None:
                try:
                    await attr.close()
                except Exception:
                    pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

    # ---- Authentication Helpers ----
    async def _set_auth_cookies(self) -> None:
        """Set authentication cookies from environment."""
        if not self._context:
            return

        cookies = []
        if settings.x_auth_token:
            cookies.append({
                "name": "auth_token",
                "value": settings.x_auth_token,
                "domain": ".twitter.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
            })
        if settings.x_csrf_token:
            cookies.append({
                "name": "ct0",
                "value": settings.x_csrf_token,
                "domain": ".twitter.com",
                "path": "/",
                "secure": True,
            })

        if cookies:
            await self._context.add_cookies(cookies)
            log.info("X/Twitter auth cookies set")

    # ---- XHR Interception ----
    async def _install_interceptor(self) -> None:
        """Install response interception for GraphQL XHR calls."""
        if not self._page:
            return

        self._page.on("response", self._on_response)

    async def _on_response(self, response) -> None:
        """Handle intercepted XHR responses."""
        try:
            url = response.url
            content_type = response.headers.get("content-type", "")

            # Only intercept JSON responses from GraphQL endpoints
            is_graphql = any(pattern in url for pattern in self.GRAPHQL_PATTERNS)
            if not is_graphql or "application/json" not in content_type:
                return

            # Parse response body
            try:
                body = await response.json()
            except Exception:
                return

            # Extract tweets/events from the response
            extracted = self._extract_tweets(body)
            for tweet in extracted:
                self.captured_tweets.append(tweet)
                await self._publish_raw_data(tweet)

        except Exception as e:
            log.debug(f"Error processing XHR response: {e}")

    # ---- Tweet Extraction ----
    def _extract_tweets(self, data: Any) -> List[Dict[str, Any]]:
        """Recursively extract tweet objects from GraphQL response JSON.

        Args:
            data: Response JSON (dict or list)

        Returns:
            List of extracted tweet dictionaries
        """
        tweets: List[Dict[str, Any]] = []

        if isinstance(data, dict):
            # Look for tweet entries
            for key, value in data.items():
                if key in ("tweet", "tweet_results", "tweetResult", "result"):
                    if isinstance(value, dict):
                        tweets.append(self._normalize_tweet(value))
                    elif isinstance(value, list):
                        for item in value:
                            if isinstance(item, dict):
                                tweets.append(self._normalize_tweet(item))
                elif key == "entries" and isinstance(value, list):
                    for entry in value:
                        tweets.extend(self._extract_tweets(entry))
                elif key in ("instructions", "timeline", "threaded_conversation_with_injections_v2"):
                    tweets.extend(self._extract_tweets(value))
                elif isinstance(value, (dict, list)):
                    tweets.extend(self._extract_tweets(value))

        elif isinstance(data, list):
            for item in data:
                tweets.extend(self._extract_tweets(item))

        return tweets

    def _normalize_tweet(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw tweet into a standard event format.

        Args:
            raw: Raw tweet dictionary from GraphQL

        Returns:
            Normalized tweet/event dictionary
        """
        # Try different nesting levels (X API changes structures)
        core = raw.get("core", {}) or raw.get("user_results", {}).get("result", {})
        legacy = raw.get("legacy", {}) or raw.get("tweet", {}).get("legacy", {})

        user_result = core.get("result", {}) if isinstance(core, dict) else {}
        user_legacy = user_result.get("legacy", {}) if isinstance(user_result, dict) else {}

        # Extract text
        full_text = legacy.get("full_text", "") or legacy.get("text", "")
        if not full_text:
            # Try note_tweet (long-form)
            note_tweet = raw.get("note_tweet", {}).get("note_tweet_results", {}).get("result", {})
            if isinstance(note_tweet, dict):
                full_text = note_tweet.get("text", "")

        # Extract entities (hashtags, mentions, URLs)
        entities = legacy.get("entities", {})
        hashtags = [h.get("text", "") for h in entities.get("hashtags", [])]
        mentions = [m.get("screen_name", "") for m in entities.get("user_mentions", [])]
        urls = [u.get("expanded_url", u.get("url", "")) for u in entities.get("urls", [])]

        # Coordinates
        geo = legacy.get("geo", {}) or legacy.get("coordinates", {})
        lat = geo.get("lat") or (geo.get("coordinates", [None, None])[1] if isinstance(geo.get("coordinates"), list) else None)
        lon = geo.get("lon") or (geo.get("coordinates", [None, None])[0] if isinstance(geo.get("coordinates"), list) else None)

        place = legacy.get("place", {}) or {}
        if not lat and place:
            bbox = place.get("bounding_box", {}).get("coordinates", [[[]]])[0]
            if bbox and len(bbox) >= 2:
                lat = (bbox[0][1] + bbox[2][1]) / 2
                lon = (bbox[0][0] + bbox[2][0]) / 2

        # Timestamp
        created_at = legacy.get("created_at", "")
        timestamp = datetime.now(timezone.utc).isoformat()
        if created_at:
            try:
                from dateutil import parser
                timestamp = parser.parse(created_at).isoformat()
            except Exception:
                pass

        return {
            "id": legacy.get("id_str", str(raw.get("rest_id", ""))),
            "text": full_text,
            "user": {
                "id": user_result.get("rest_id", ""),
                "screen_name": user_legacy.get("screen_name", ""),
                "name": user_legacy.get("name", ""),
                "followers_count": user_legacy.get("followers_count", 0),
                "verified": user_legacy.get("verified", False),
            },
            "hashtags": hashtags,
            "mentions": mentions,
            "urls": urls,
            "latitude": lat,
            "longitude": lon,
            "retweet_count": legacy.get("retweet_count", 0),
            "favorite_count": legacy.get("favorite_count", 0),
            "reply_count": legacy.get("reply_count", 0),
            "quote_count": legacy.get("quote_count", 0),
            "lang": legacy.get("lang", ""),
            "created_at": timestamp,
            "ingestion_timestamp": datetime.utcnow().isoformat(),
            "source": "x_twitter_cdp",
        }

    # ---- Scraping Loop ----
    async def _scrape_loop(self) -> None:
        """Main scraping loop - navigates, scrolls, captures."""
        if not self._page:
            log.error("Browser page not initialized")
            return

        # Navigate to X/Twitter
        target_urls = [
            "https://twitter.com/home",  # Timeline
            "https://twitter.com/explore",  # Trends
        ]

        last_nav = 0.0
        NAV_INTERVAL = 60.0  # seconds between navigations

        while self.running:
            try:
                now = time.time()
                if now - last_nav >= NAV_INTERVAL:
                    url = target_urls[int(now / NAV_INTERVAL) % len(target_urls)]
                    try:
                        await self._page.goto(
                            url,
                            wait_until="networkidle",
                            timeout=30000,
                        )
                        log.info(f"Navigated to {url}")
                    except Exception as e:
                        log.warning(f"Navigation failed for {url}: {e}")
                        # Try to continue - page may still be usable
                    last_nav = now

                # Scroll to trigger more content
                await self._page.evaluate("window.scrollBy(0, window.innerHeight)")
                await asyncio.sleep(3)

                # Occasionally scroll to top
                if int(now) % 30 < 3:
                    await self._page.evaluate("window.scrollTo(0, 0)")
                    await asyncio.sleep(2)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.error(f"Error in scrape loop: {e}")
                await asyncio.sleep(5)

    # ---- Publishing ----
    async def _publish_raw_data(self, data: Dict[str, Any]) -> None:
        """Publish raw tweet data to NATS subject 'osint.x.raw'.

        Args:
            data: Normalized tweet/event data
        """
        try:
            message = json.dumps(data).encode("utf-8")
            await self.nats_client.publish("osint.x.raw", message)
            log.debug(f"Published tweet {data.get('id', 'unknown')[:20]}")
        except Exception as e:
            log.error(f"Failed to publish tweet to NATS: {e}")

    # ---- Helper Methods ----
    async def get_tweet_count(self) -> int:
        """Get total captured tweet count."""
        return len(self.captured_tweets)

    async def get_recent_tweets(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get most recent captured tweets."""
        return self.captured_tweets[-count:]

    async def search_tweets(self, keyword: str) -> List[Dict[str, Any]]:
        """Search captured tweets by keyword."""
        keyword_lower = keyword.lower()
        return [
            t for t in self.captured_tweets
            if keyword_lower in t.get("text", "").lower()
        ]

    async def reset(self) -> None:
        """Reset captured tweets (for testing)."""
        self.captured_tweets.clear()
        log.info("Captured tweets reset")