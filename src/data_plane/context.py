"""Data Plane Task-Isolated Context Variables and Context Resolution.

Provides task-isolated ContextVar for propagating user identity context
across async execution tasks without cyclic dependencies.
"""

from contextvars import ContextVar

from src.data_plane.schemas import DataPlaneUserContext

user_context_var: ContextVar[DataPlaneUserContext | None] = ContextVar(
    "user_context_var", default=None
)


def get_current_user_context() -> DataPlaneUserContext | None:
    """Returns the DataPlaneUserContext for the active task execution context."""
    return user_context_var.get()


__all__ = ["user_context_var", "get_current_user_context"]
