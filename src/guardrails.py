"""
Guardrails — tool allowlist, output validation, and step budget enforcement.
"""
from __future__ import annotations

import threading
from typing import Any

from .schemas import ActionItem, ToolName


# ---------------------------------------------------------------------------
# Tool allowlist
# ---------------------------------------------------------------------------

ALLOWED_TOOLS: set[str] = {
    ToolName.TRANSCRIPT_PARSE.value,
    ToolName.TASK_CLASSIFY.value,
    ToolName.PRIORITY_SCORE.value,
    ToolName.EXTRACT_ACTION_ITEMS.value,
    ToolName.DEDUPLICATE.value,
}


def validate_tool_call(tool_name: str) -> None:
    """Raise ValueError if *tool_name* is not in the allowlist."""
    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(
            f"Guardrail: tool '{tool_name}' is not in the allowed tool list. "
            f"Allowed: {sorted(ALLOWED_TOOLS)}"
        )


# ---------------------------------------------------------------------------
# Output schema validation
# ---------------------------------------------------------------------------

def validate_output(items: list[Any]) -> list[ActionItem]:
    """
    Validate that every item in *items* is (or can be coerced to) a valid
    ActionItem.  Returns a list of validated ActionItem objects.
    Raises ValueError if any item fails validation.
    """
    validated: list[ActionItem] = []
    for i, raw in enumerate(items):
        if isinstance(raw, ActionItem):
            validated.append(raw)
        elif isinstance(raw, dict):
            try:
                validated.append(ActionItem.model_validate(raw))
            except Exception as exc:
                raise ValueError(f"Guardrail: item[{i}] failed schema validation: {exc}") from exc
        else:
            raise ValueError(
                f"Guardrail: item[{i}] has unexpected type {type(raw).__name__}"
            )
    return validated


# ---------------------------------------------------------------------------
# Soft timeout context manager
# ---------------------------------------------------------------------------

class ToolTimeoutError(RuntimeError):
    """Raised when a tool call exceeds its allowed time budget."""


class TimeoutGuard:
    """
    Context manager that fires a callback (default: raise ToolTimeoutError)
    after *seconds* seconds using a background thread timer.

    Usage::

        with TimeoutGuard(seconds=10, tool_name="transcript_parse"):
            result = slow_tool(...)
    """

    def __init__(self, seconds: float, tool_name: str = "unknown") -> None:
        self._seconds = seconds
        self._tool_name = tool_name
        self._timer: threading.Timer | None = None
        self._timed_out = False

    def _on_timeout(self) -> None:
        self._timed_out = True  # can't raise from a thread, mark for __exit__

    def __enter__(self) -> "TimeoutGuard":
        timer = threading.Timer(self._seconds, self._on_timeout)
        timer.daemon = True
        timer.start()
        self._timer = timer
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> bool:
        timer = self._timer
        if timer is not None:
            timer.cancel()
        if self._timed_out:
            raise ToolTimeoutError(
                f"Guardrail: tool '{self._tool_name}' timed out after {self._seconds}s"
            )
        return False  # don't suppress exceptions
