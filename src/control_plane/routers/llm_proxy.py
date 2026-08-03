"""LLM Proxy APIRouter.

Serves OpenAI-compatible `/v1/chat/completions` endpoint backed by lightweight `httpx`,
injecting operational cost and token usage headers into every client response.
"""

from typing import Any

from fastapi import APIRouter, Response

from src.control_plane.services.llm_router import LLMRouterService

router = APIRouter(prefix="/v1", tags=["LLM Proxy Router"])
llm_service = LLMRouterService()


@router.post("/chat/completions")
async def chat_completions_proxy(payload: dict[str, Any], response: Response):
    """Proxy endpoint for LLM completion calls injecting cost/token metadata headers."""
    payload_res, headers_to_inject = await llm_service.route_completion(payload)

    for h_key, h_val in headers_to_inject.items():
        response.headers[h_key] = h_val

    return payload_res
