# ============================================================================
# Project Panopticon - AI Orchestrator Router (OpenRouter + Tavily)
# ============================================================================

import json
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException
import structlog

from config import settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/query")
async def ai_query(query: Dict[str, Any]) -> Dict[str, Any]:
    """Proxy AI query to OpenRouter and return structured JSON action."""
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OpenRouter API key not configured")

    try:
        user_query = query.get("query", "")
        viewport = query.get("viewport", {
            "lat": 44.0,
            "lon": 31.0,
            "height": 20000000,
        })
        active_layers = query.get("active_layers", [])

        # Build context for the spatial analyst
        system_prompt = {
            "role": "system",
            "content": """You are a spatial OSINT analyst assistant. Return actionable JSON.

Respond ONLY with a JSON object containing an "action" field. Possible actions:
- {"action": "camera.trackEntity", "entity_id": "<id>"}
- {"action": "camera.flyTo", "lat": <float>, "lon": <float>, "height": <float>}
- {"action": "query.events", "query": "<SurrealDB query>"}
- {"action": "query.aircraft", "icao_hex": "<hex>"}
- {"action": "alert", "message": "<string>"}""",
        }

        user_context = {
            "role": "user",
            "content": f"""[CURRENT_UI_STATE]
- Viewport: Lat {viewport.get('lat')}, Lon {viewport.get('lon')}, Height {viewport.get('height')}
- Active Layers: {active_layers}

[USER_QUERY]
"{user_query}"

Return a JSON action to execute.""",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openrouter_model,
                    "messages": [system_prompt, user_context],
                    "max_tokens": 200,
                    "temperature": 0.1,
                },
                timeout=30.0,
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Try to parse JSON from response
            try:
                action = json.loads(content)
                return {
                    "success": True,
                    "action": action,
                    "raw_response": content,
                }
            except json.JSONDecodeError:
                return {
                    "success": True,
                    "action": {"action": "alert", "message": f"AI Response: {content}"},
                    "raw_response": content,
                }

    except HTTPException:
        raise
    except Exception as e:
        log.error(f"AI query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models")
async def get_available_models() -> List[Dict[str, str]]:
    """Get available OpenRouter models."""
    if not settings.openrouter_api_key:
        raise HTTPException(status_code=503, detail="OpenRouter API key not configured")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
                timeout=10.0,
            )
            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            data = response.json()
            return [
                {"id": m["id"], "name": m.get("name", m["id"])}
                for m in data.get("data", [])[:20]
            ]

    except Exception as e:
        log.error(f"Failed to fetch models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/tavily")
async def tavily_search(query: Dict[str, Any]) -> Dict[str, Any]:
    """Search the web via Tavily Search API for context injection."""
    if not settings.tavily_api_key:
        raise HTTPException(status_code=503, detail="Tavily API key not configured")

    try:
        search_query = query.get("query", "")
        max_results = query.get("max_results", 5)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.tavily.com/search",
                headers={
                    "Content-Type": "application/json",
                },
                json={
                    "api_key": settings.tavily_api_key,
                    "query": search_query,
                    "max_results": max_results,
                    "search_depth": "basic",
                },
                timeout=15.0,
            )

            if response.status_code != 200:
                raise HTTPException(status_code=response.status_code, detail=response.text)

            data = response.json()
            return {
                "success": True,
                "query": search_query,
                "results": data.get("results", []),
                "answer": data.get("answer", ""),
            }

    except Exception as e:
        log.error(f"Tavily search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
