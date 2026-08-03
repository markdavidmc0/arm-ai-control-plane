"""Live GKE & LLM Agent Performance Scenario Benchmarks.

Evaluates multi-turn LLM agent tasks comparing Code Mode (static catalog)
against sequential MCP tool calling. Requires live LLM API credentials or --run-benchmarks.
"""

from typing import Any

import pytest


async def run_agent_loop(mode: str, problem: str, api_client) -> dict[str, Any]:
    """Simulates a multi-turn LLM agent execution loop routing through Control Plane endpoints.

    Args:
        mode: Execution mode ('direct' for Classic, 'codemode' for Code Mode).
        problem: Prompt problem statement / source code.
        api_client: Async client for HTTP requests (in-memory or live).

    Returns:
        Dict containing total 'turns', 'prompt_tokens', 'completion_tokens', and 'completed' status.
    """
    max_turns = 5
    turn_count = 0
    total_prompt_tokens = 0
    total_completion_tokens = 0
    completed = False

    messages = [{"role": "user", "content": problem}]

    for turn in range(1, max_turns + 1):
        turn_count = turn
        llm_payload = {
            "model": "claude-3-5-sonnet",
            "messages": messages,
            "execution_mode": mode,
            "use_gvisor": True,
        }

        headers = {}
        if mode == "codemode":
            headers["X-Workspace-Context"] = "physical-ai"

        res = await api_client.post("/v1/chat/completions", json=llm_payload, headers=headers)
        assert res.status_code == 200
        res_data = res.json()
        prompt_tokens = int(res.headers.get("X-LLM-Prompt-Tokens", "100"))

        total_prompt_tokens += prompt_tokens
        completion_tokens = res_data.get("usage", {}).get("completion_tokens", 120)
        total_completion_tokens += completion_tokens

        choice = res_data["choices"][0]
        finish_reason = choice.get("finish_reason")

        if mode == "direct" and turn == 1:
            tool_call_payload = {
                "name": "profile_and_optimize_kernel",
                "arguments": {"source_code": problem},
            }
            tool_res = await api_client.post("/api/v1/registry/call", json=tool_call_payload)
            assert tool_res.status_code == 200
            tool_output = tool_res.json()

            messages.append(
                {
                    "role": "assistant",
                    "content": "Executing profile_and_optimize_kernel",
                }
            )
            messages.append({"role": "tool", "content": str(tool_output)})
        else:
            if finish_reason == "stop" or not choice.get("message", {}).get("tool_calls"):
                completed = True
                break

    return {
        "turns": turn_count,
        "prompt_tokens": total_prompt_tokens,
        "completion_tokens": total_completion_tokens,
        "completed": completed,
    }


# ==============================================================================
# Code Mode vs. Classic Benchmarking
# ==============================================================================


@pytest.mark.heavy
@pytest.mark.asyncio
async def test_code_mode_vs_classic_benchmarking(api_client, target_env, llm_enabled):
    """Compare Classic tool calling vs Code Mode execution via real HTTP agent loops."""
    if not llm_enabled:
        pytest.skip(
            "Scenario benchmarking requires live GKE and LLM credentials (or --run-benchmarks)."
        )

    problem = "void matmul_opt() { /* Optimize SME2 kernel */ }"

    classic_res = await run_agent_loop("direct", problem, api_client=api_client)
    code_mode_res = await run_agent_loop("codemode", problem, api_client=api_client)

    assert classic_res["completed"] is True
    assert code_mode_res["completed"] is True
    assert classic_res["turns"] <= 5
    assert code_mode_res["turns"] <= 5
    assert code_mode_res["turns"] < classic_res["turns"]
    assert code_mode_res["prompt_tokens"] < classic_res["prompt_tokens"]
