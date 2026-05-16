"""InterruptHandler module for managing agent execution interrupts per AEF RFC-0003."""

from typing import Optional
from event_bus import EventBus


class InterruptHandler:
    """Handles agent execution interrupts with event emission."""

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus
        self._interrupted: bool = False
        self._last_success_event_id: Optional[str] = None
        self._interrupt_event_id: Optional[str] = None

    def is_interrupted(self) -> bool:
        """Return whether the agent is currently interrupted."""
        return self._interrupted

    def get_last_success_event_id(self) -> str:
        """Return the last non-interrupt event id before interruption."""
        if self._last_success_event_id is None:
            raise RuntimeError("No success event recorded yet.")
        return self._last_success_event_id

    def update_last_success_event_id(self, event_id: str) -> None:
        """Update the last success event id (called by external after each emit)."""
        if not self._interrupted:
            self._last_success_event_id = event_id

    def interrupt(self, reason: str, source: str = "system") -> str:
        """Interrupt agent execution.

        Args:
            reason: Interrupt reason (e.g., timeout, human_request, resource_exhausted).
            source: Interrupt source, either "system" or "human".

        Returns:
            Event ID of the agent.interrupted event.
        """
        if self._interrupted:
            raise RuntimeError("Agent is already interrupted. Nested interrupts are not allowed.")

        if source not in ("system", "human"):
            raise ValueError(f"Invalid source: {source}. Must be 'system' or 'human'.")

        self._interrupt_event_id = self._bus.emit(
            action="agent.interrupted",
            actor=source,
            payload={"reason": reason, "source": source},
        )
        self._interrupted = True
        return self._interrupt_event_id

    def resolve(self) -> str:
        """Resolve the interrupt and resume execution.

        Returns:
            Event ID of the agent.interrupt.resolved event.
        """
        if not self._interrupted:
            raise RuntimeError("No active interrupt to resolve.")

        resolved_id = self._bus.emit(
            action="agent.interrupt.resolved",
            actor="system",
            payload={"resumed_from_event_id": self._interrupt_event_id},
        )
        self._interrupted = False
        self._interrupt_event_id = None
        return resolved_id
