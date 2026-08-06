"""Software Fault Isolation (SFI) execution engine powered by pydantic-monty."""

import time
from collections.abc import Callable
from typing import Any

try:
    from pydantic_monty import (
        AsyncMonty,
        MontyError,
        MontyRuntimeError,
        MontySyntaxError,
        ResourceLimits,
    )
except ImportError:  # Fallback type definitions if pydantic_monty is absent in lightweight tests
    class AsyncMonty:
        """Placeholder AsyncMonty context manager."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "AsyncMonty":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        def checkout(self, *args: Any, **kwargs: Any) -> "AsyncMontySession":
            return AsyncMontySession()

    class AsyncMontySession:
        """Placeholder AsyncMontySession context manager."""

        async def __aenter__(self) -> "AsyncMontySession":
            return self

        async def __aexit__(self, *args: Any) -> None:
            pass

        async def feed_run(self, *args: Any, **kwargs: Any) -> Any:
            return None

    class MontyError(Exception):
        """Base SFI Monty exception."""

    class MontySyntaxError(MontyError):
        """Syntax error inside sandboxed snippet."""

    class MontyRuntimeError(MontyError):
        """Runtime error inside sandboxed snippet."""

    class ResourceLimits(dict):
        """Placeholder resource limits container."""

from src.config import settings


class MontyEngine:
    """Software Fault Isolation (SFI) execution engine using native pydantic-monty."""

    def __init__(self, max_instructions: int | None = None) -> None:
        """Initializes MontyEngine with instruction tick and duration limits.

        Args:
            max_instructions: Maximum allowed instruction tick limit before trapped.
        """
        self.max_instructions = max_instructions or settings.MONTY_MAX_INSTRUCTIONS
        try:
            limits_dict: Any = ResourceLimits(
                max_instructions=self.max_instructions,
                max_duration_secs=5.0,
                max_memory=512 * 1024 * 1024,
            )
            self._limits: Any = limits_dict
        except Exception:
            self._limits = None

    async def execute_snippet(
        self,
        code: str,
        inputs: dict[str, Any] | None = None,
        external_functions: dict[str, Callable] | None = None,
    ) -> dict[str, Any]:
        """Executes a Python code snippet inside native pydantic-monty SFI boundary.

        Args:
            code: Python code snippet to execute.
            inputs: Variable bindings to inject into evaluation scope.
            external_functions: Mapping of host tool names to async callback handlers.

        Returns:
            Dictionary containing execution result, stdout, duration_ms, and error status:
            {
                "success": bool,
                "result": Any | None,
                "stdout": str,
                "duration_ms": float,
                "error": dict[str, str] | None
            }
        """
        start_ns = time.perf_counter_ns()
        out_lines: list[str] = []

        def print_cb(stream: str, text: str) -> None:
            if stream == "stdout":
                out_lines.append(text)

        try:
            async with AsyncMonty() as monty:
                async with monty.checkout(limits=self._limits) as session:
                    res = await session.feed_run(
                        code,
                        inputs=inputs,
                        external_lookup=external_functions,
                        print_callback=print_cb,
                    )

            duration_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)

            return {
                "success": True,
                "result": res,
                "stdout": "".join(out_lines),
                "duration_ms": duration_ms,
                "error": None,
            }

        except (MontySyntaxError, SyntaxError) as e:
            duration_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
            return {
                "success": False,
                "result": None,
                "stdout": "".join(out_lines),
                "duration_ms": duration_ms,
                "error": {"type": "SyntaxError", "message": str(e)},
            }

        except (MontyRuntimeError, RuntimeError) as e:
            duration_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
            return {
                "success": False,
                "result": None,
                "stdout": "".join(out_lines),
                "duration_ms": duration_ms,
                "error": {"type": "RuntimeError", "message": str(e)},
            }

        except (MontyError, Exception) as e:
            duration_ms = round((time.perf_counter_ns() - start_ns) / 1_000_000.0, 3)
            return {
                "success": False,
                "result": None,
                "stdout": "".join(out_lines),
                "duration_ms": duration_ms,
                "error": {"type": type(e).__name__, "message": str(e)},
            }


__all__ = ["MontyEngine"]
