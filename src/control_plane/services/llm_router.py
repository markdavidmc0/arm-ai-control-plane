"""Async Cloud-Agnostic LLM Proxy Router Service using LiteLLM.

Forwards `/v1/chat/completions` requests to multi-provider backends (Anthropic, OpenAI, Gemini)
using `litellm.acompletion`. Computes costs via `completion_cost` and injects telemetry headers:
- `X-LLM-Cost-USD`
- `X-LLM-Prompt-Tokens`
- `X-LLM-Completion-Tokens`
- `X-LLM-Latency-MS`
- `X-LLM-Provider`
"""

import logging
import os
import time
from typing import Any

import litellm

logger = logging.getLogger("mvcp.llm_router")


class LLMRouterService:
    """Async cloud-agnostic proxy router for LLM completions with cost header injection."""

    def __init__(self, auth_service: Any | None = None):
        self.auth_service = auth_service

    async def route_completion(
        self, request_data: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, str]]:
        """Routes completion payload via litellm.acompletion and computes metadata headers.

        Args:
            request_data: OpenAI-compatible `/v1/chat/completions` request body.

        Returns:
            Tuple of (response_payload_dict, headers_to_inject_dict).

        Raises:
            Exception: If litellm.acompletion fails.
        """
        start_time = time.time()
        model = request_data.get("model", "claude-3-5-sonnet")
        messages = request_data.get("messages", [])

        # Build litellm.acompletion keyword arguments
        completion_kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        # Dynamic GCP configuration
        gcp_project = os.environ.get("GCP_PROJECT_ID", "sovereign-ai-495715")
        gcp_location = os.environ.get("GCP_LOCATION", "us-central1")

        # Vertex AI / Gemini routing using ambient GKE Workload Identity / ADC
        if model.startswith("vertex_ai") or "gemini" in model.lower():
            completion_kwargs["custom_llm_provider"] = "vertex_ai"
            completion_kwargs["vertex_project"] = gcp_project
            completion_kwargs["vertex_location"] = gcp_location

        # Optional parameters to forward if present
        for param in ["temperature", "top_p", "max_tokens", "tools", "stream"]:
            if param in request_data and request_data[param] is not None:
                completion_kwargs[param] = request_data[param]

        try:
            response = await litellm.acompletion(**completion_kwargs)
        except Exception as e:
            logger.error(f"[LLMRouterService] litellm.acompletion failed for model {model}: {e}")
            raise

        latency_ms = round((time.time() - start_time) * 1000.0, 2)

        # Convert ModelResponse or dict to standard dictionary
        if hasattr(response, "model_dump"):
            response_payload = response.model_dump()
        elif hasattr(response, "dict"):
            response_payload = response.dict()
        elif isinstance(response, dict):
            response_payload = response
        else:
            response_payload = dict(response)

        # Calculate cost via litellm.completion_cost
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

        # Token usage extraction
        usage = response_payload.get("usage", {}) or {}
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)

        # Model / Provider identification
        provider_name = response_payload.get("model", model) or "arm-mvcp-gateway"

        headers = {
            "X-LLM-Cost-USD": str(cost_usd),
            "X-LLM-Prompt-Tokens": str(prompt_tokens),
            "X-LLM-Completion-Tokens": str(completion_tokens),
            "X-LLM-Latency-MS": str(latency_ms),
            "X-LLM-Provider": str(provider_name),
        }

        return response_payload, headers
