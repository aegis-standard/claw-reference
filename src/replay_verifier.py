"""ReplayVerifier module for validating event replay legality per AEF RFC-0002."""

import copy
from datetime import datetime, UTC
from typing import Any


class ReplayVerifier:
    """Verifies replay legality against original event stream."""

    def __init__(self, original_events: list[dict], replayed_events: list[dict]) -> None:
        self._original = original_events
        self._replayed = replayed_events
        self._session_id: str = ""
        if original_events:
            self._session_id = original_events[0].get("session_id", "")

    def verify(self) -> dict:
        order_ok = self._check_event_order()
        causality_ok = self._check_causality()
        deterministic_ok = self._check_deterministic()

        status = "VALID" if (order_ok and causality_ok and deterministic_ok) else "INVALID"
        first_id, desc = self._first_mismatch

        return {
            "session_id": self._session_id,
            "replayed_at": datetime.now(UTC).isoformat(),
            "replay_runtime": "claw-reference",
            "status": status,
            "conditions": {
                "event_order_preserved": order_ok,
                "causality_chain_intact": causality_ok,
                "deterministic_match": deterministic_ok,
            },
            "details": {
                "first_mismatch_event_id": first_id,
                "mismatch_description": desc,
            },
            "original_event_count": len(self._original),
            "replayed_event_count": len(self._replayed),
        }

    def _check_event_order(self) -> bool:
        orig_actions = [e.get("action") for e in self._original]
        replay_actions = [e.get("action") for e in self._replayed]
        if orig_actions != replay_actions:
            self._first_mismatch = (
                self._replayed[0].get("id") if self._replayed else None,
                "Event order mismatch",
            )
            return False
        return True

    def _check_causality(self) -> bool:
        seen_ids: set[str] = set()
        for i, event in enumerate(self._replayed):
            eid = event.get("id", "")
            cid = event.get("causality_id")
            if i == 0:
                if cid is not None:
                    self._first_mismatch = (eid, "First event must have null causality_id")
                    return False
            else:
                if cid is None:
                    self._first_mismatch = (eid, "Non-first event has null causality_id")
                    return False
                if cid not in seen_ids:
                    self._first_mismatch = (eid, "Causality chain broken")
                    return False
                if cid == eid:
                    self._first_mismatch = (eid, "Causality loop detected")
                    return False
            seen_ids.add(eid)
        return True

    def _check_deterministic(self) -> bool:
        for orig, replay in zip(self._original, self._replayed):
            action = orig.get("action")
            if action == "tool.call.started":
                if not self._deep_match(orig.get("payload", {}).get("input"),
                                        replay.get("payload", {}).get("input")):
                    self._first_mismatch = (replay.get("id"),
                                            "Deterministic mismatch in tool.call.started input")
                    return False
            elif action == "tool.call.completed":
                if not self._deep_match(orig.get("payload", {}).get("output"),
                                        replay.get("payload", {}).get("output")):
                    self._first_mismatch = (replay.get("id"),
                                            "Deterministic mismatch in tool.call.completed output")
                    return False
        return True

    _first_mismatch: tuple[str | None, str | None] = (None, None)

    @staticmethod
    def _deep_match(original: Any, replayed: Any) -> bool:
        if type(original) != type(replayed):
            return False
        if isinstance(original, float):
            return abs(original - replayed) <= 1e-6
        if isinstance(original, dict):
            if set(original.keys()) != set(replayed.keys()):
                return False
            for key in original:
                if not ReplayVerifier._deep_match(original[key], replayed[key]):
                    return False
            return True
        if isinstance(original, list):
            if len(original) != len(replayed):
                return False
            for o, r in zip(original, replayed):
                if not ReplayVerifier._deep_match(o, r):
                    return False
            return True
        return original == replayed