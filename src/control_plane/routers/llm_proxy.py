"""LLM Proxy APIRouter.

Serves OpenAI-compatible `/v1/chat/completions` endpoint backed by LiteLLM,
injecting operational cost and token usage headers into every client response.
"""

from typing import Any
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from src.control_plane.dependencies import (
    get_llm_router_service,
    verify_authentication,
)
from src.control_plane.services.llm_router import LLMRouterService

router = APIRouter(prefix="/v1", tags=["LLM Proxy Router"])


@router.post("/chat/completions")
async def chat_completions_proxy(
    payload: dict[str, Any],
    response: Response,
    auth_data: dict[str, Any] = Depends(verify_authentication),
    llm_service: LLMRouterService = Depends(get_llm_router_service),
):
    """Proxy endpoint for LLM completion calls injecting cost/token metadata headers."""
    if "messages" not in payload or not isinstance(payload["messages"], list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Field 'messages' must be a non-empty list.",
        )

    try:
        payload_res, headers_to_inject = await llm_service.route_completion(payload)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM Provider execution failed: {str(err)}",
        )

    for h_key, h_val in headers_to_inject.items():
        response.headers[h_key] = h_val

    return payload_res
