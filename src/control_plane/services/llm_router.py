"""Async Cloud-Agnostic LLM Proxy Router Service using LiteLLM.

Forwards `/v1/chat/completions` requests to multi-provider backends (Anthropic, OpenAI, Gemini)
via an injected LLM execution client. Computes costs via `completion_cost` and injects telemetry
headers:
- `X-LLM-Cost-USD`
- `X-LLM-Prompt-Tokens`
- `X-LLM-Completion-Tokens`
- `X-LLM-Latency-MS`
- `X-LLM-Provider`
"""

import logging
import os
import time
from typing import Any, Protocol

import litellm

logger = logging.getLogger("mvcp.llm_router")


class LLMClientProtocol(Protocol):
    """Protocol for LLM completion execution."""

    async def acompletion(self, **kwargs: Any) -> Any:
        """Executes async completion call."""
        ...


class LiteLLMClient:
    """Default production client wrapping LiteLLM's async completion execution."""

    async def acompletion(self, **kwargs: Any) -> Any:
        """Executes LiteLLM async completion call."""
        return await litellm.acompletion(**kwargs)


class LLMRouterService:
    """Async cloud-agnostic proxy router for LLM completions with cost header injection."""

    def __init__(self, llm_client: LLMClientProtocol | None = None) -> None:
        """Initialize router with an optional custom LLM client backend.

        Defaults to LiteLLMClient for production.
        """
        self.llm_client = llm_client or LiteLLMClient()

    async def route_completion(
        self, request_data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Routes completion payload via injected client and computes metadata headers.

        Args:
            request_data: OpenAI-compatible `/v1/chat/completions` request body.

        Returns:
            Tuple of (response_payload_dict, headers_to_inject_dict).

        Raises:
            Exception: If client execution fails.
        """
        start_time = time.time()
        model = request_data.get("model", "openai/gpt-4o")
        messages = request_data.get("messages", [])

        completion_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # GCP configuration without hardcoded values
        gcp_project = os.environ.get("GCP_PROJECT_ID")
        gcp_location = os.environ.get("GCP_LOCATION", "us-central1")

        if model.startswith("vertex_ai") or "gemini" in model.lower():
            completion_kwargs["custom_llm_provider"] = "vertex_ai"
            if gcp_project:
                completion_kwargs["vertex_project"] = gcp_project
            completion_kwargs["vertex_location"] = gcp_location

        # Optional parameter forwarding
        for param in ["temperature", "top_p", "max_tokens", "tools", "stream"]:
            if param in request_data and request_data[param] is not None:
                completion_kwargs[param] = request_data[param]

        try:
            # Delegated to injected client dependency
            response = await self.llm_client.acompletion(**completion_kwargs)
        except (litellm.APIError, litellm.exceptions.APIError) as provider_err:
            logger.error(
                f"[LLMRouterService] LiteLLM provider error for model [{model}]: {provider_err}"
            )
            raise
        except Exception as e:
            logger.error(f"[LLMRouterService] Unexpected execution error for model [{model}]: {e}")
            raise

        latency_ms = round((time.time() - start_time) * 1000.0, 2)

        # Response normalization
        if hasattr(response, "model_dump"):
            response_payload = response.model_dump()
        elif hasattr(response, "dict"):
            response_payload = response.dict()
        elif isinstance(response, dict):
            response_payload = response
        else:
            response_payload = dict(response)

        # Telemetry calculations
        try:
            cost = litellm.completion_cost(completion_response=response)
            cost_usd = f"{cost:.6f}" if cost is not None else "0.000000"
        except (ValueError, KeyError, AttributeError, TypeError) as price_err:
            logger.info(
                f"[LLMRouterService] Pricing for model [{model}] unavailable in LiteLLM catalog "
                f"({price_err}). Setting X-LLM-Cost-USD header to 0.000000."
            )
            cost_usd = "0.000000"
        except Exception as unhandled_cost_err:
            logger.exception(
                f"[LLMRouterService] Unexpected error during completion cost calculation for "
                f"model [{model}]: {unhandled_cost_err}"
            )
            cost_usd = "0.000000"

        usage = response_payload.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        raw_model = response_payload.get("model", model) or "arm-mvcp-gateway"
        provider_name = raw_model.split("/")[0] if "/" in raw_model else raw_model

        headers = {
            "X-LLM-Cost-USD": str(cost_usd),
            "X-LLM-Prompt-Tokens": str(prompt_tokens),
            "X-LLM-Completion-Tokens": str(completion_tokens),
            "X-LLM-Latency-MS": str(latency_ms),
            "X-LLM-Provider": str(provider_name),
        }

        return response_payload, headers
