"""CodeMode Python SDK Bridge (arm_tools).

Exposes method calls (`arm_tools.my_tool(...)`) inside CodeMode REPL scripts that
automatically route calls through LocalToolDispatcher to multi-language executables.
"""

import asyncio
import logging
from typing import Any

from src.data_plane.worker.tool_dispatcher import LocalToolDispatcher

logger = logging.getLogger("mvcp.arm_tools_bridge")


class ArmToolsSDKBridge:
    """Python SDK bridge client exposed inside CodeMode Python execution environments.

    Allows LLM scripts to call tool functions naturally (e.g. `arm_tools.profile_and_optimize_kernel(...)`
    or `arm_tools.ros2_pointcloud_voxelizer_profile(...)`).
    """

    def __init__(self, dispatcher: LocalToolDispatcher | None = None):
        self.dispatcher = dispatcher or LocalToolDispatcher()

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Synchronous or awaitable entry point for calling registered platform tools.

        Args:
            tool_name: Target tool name.
            **kwargs: Tool call arguments.

        Returns:
            Execution result dictionary.
        """
        try:
            loop = asyncio.get_running_loop()
            # If running inside active async loop, create task or execute
            return loop.create_task(self.dispatcher.dispatch_tool_call(tool_name, kwargs))
        except RuntimeError:
            # If no running event loop, execute synchronously
            return asyncio.run(self.dispatcher.dispatch_tool_call(tool_name, kwargs))

    async def acall_tool(self, tool_name: str, **kwargs: Any) -> dict[str, Any]:
        """Async entry point for executing tools inside `asyncio.gather` parallel chains.

        Args:
            tool_name: Target tool name.
            **kwargs: Tool call arguments.

        Returns:
            Execution result dictionary.
        """
        return await self.dispatcher.dispatch_tool_call(tool_name, kwargs)

    def __getattr__(self, name: str) -> Any:
        """Dynamic attribute access turning `arm_tools.my_tool(...)` into tool dispatch calls."""
        if name.startswith("_"):
            raise AttributeError(f"'ArmToolsSDKBridge' object has no attribute '{name}'")

        def tool_wrapper(*args: Any, **kwargs: Any) -> Any:
            # Merge positional code arg if passed
            if args and "code" not in kwargs and "source_code" not in kwargs:
                kwargs["code"] = args[0]
            return self.acall_tool(name, **kwargs)

        return tool_wrapper


# Instantiate global singleton bridge instance for CodeMode REPL injection
arm_tools = ArmToolsSDKBridge()
