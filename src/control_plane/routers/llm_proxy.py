"""LLM Proxy APIRouter.

Serves OpenAI-compatible `/v1/chat/completions` endpoint backed by LiteLLM,
injecting operational cost and token usage headers into every client response.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.control_plane.dependencies import (
    UserContext,
    get_llm_router_service,
    get_user_context,
)
from src.control_plane.services.llm_router import LLMRouterService

router = APIRouter(prefix="/v1", tags=["LLM Proxy Router"])


@router.post("/chat/completions")
async def chat_completions_proxy(
    payload: dict[str, Any],
    response: Response,
    user: UserContext = Depends(get_user_context),
    llm_service: LLMRouterService = Depends(get_llm_router_service),
):
    """Proxy endpoint for LLM completion calls injecting cost/token metadata headers.

    Args:
        payload: OpenAI-compatible completion request payload dictionary.
        response: FastAPI response object for injecting cost headers.
        user: Pre-authenticated UserContext injected downstream by Envoy Edge Guard.
        llm_service: LLMRouterService instance for model completion routing.

    Returns:
        JSON response payload from the LLM provider.

    Raises:
        HTTPException: 400 Bad Request if 'messages' field is missing or invalid.
        HTTPException: 502 Bad Gateway if LLM execution fails.
    """
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
