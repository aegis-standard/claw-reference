"""HumanOverrideHandler module for managing human overrides per AEF RFC-0005."""

from typing import Optional
from event_bus import EventBus


class HumanOverrideHandler:
    """Handles human overrides of agent outputs."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._last_override: Optional[dict] = None

    def override(
        self,
        original_output: str,
        corrected_output: str,
        reason: str,
        related_event_id: Optional[str] = None,
        scope: str = "full",
    ) -> str:
        """Override agent output with human correction.

        Args:
            original_output: Agent original output before override.
            corrected_output: Human corrected output.
            reason: Override reason.
            related_event_id: Event id of the agent output being overridden.
            scope: "full" or "partial", defaults to "full".

        Returns:
            Event ID of the human.override event.
        """
        if scope not in ("full", "partial"):
            raise ValueError(f"Invalid scope: {scope}. Must be 'full' or 'partial'.")

        # Override chain: use previous corrected_output as original if not explicitly different
        if self._last_override and original_output == self._last_override["corrected_output"]:
            pass  # Chain is correct
        elif self._last_override and original_output == "":
            original_output = self._last_override["corrected_output"]

        payload: dict = {
            "original_output": original_output,
            "corrected_output": corrected_output,
            "override_reason": reason,
            "override_scope": scope,
        }
        if related_event_id is not None:
            payload["related_event_id"] = related_event_id

        event_id = self._bus.emit(
            action="human.override",
            actor="human",
            agent_id=None,
            payload=payload,
        )

        self._last_override = {
            "event_id": event_id,
            "original_output": original_output,
            "corrected_output": corrected_output,
            "reason": reason,
            "scope": scope,
        }

        return event_id

    def get_last_override(self) -> Optional[dict]:
        """Return the last override info, or None if no override occurred."""
        return self._last_override

    def is_overridden(self) -> bool:
        """Return whether any override has occurred in this session."""
        return self._last_override is not None