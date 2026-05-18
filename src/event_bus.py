"""EventBus module for append-only event logging with integrity verification."""

import json
import uuid
import hashlib
import warnings
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional


class EventBus:
    """Append-only event bus with SHA-256 integrity hashing."""

    def __init__(self, log_path: str = "~/.claw/evidence.jsonl") -> None:
        """Initialize EventBus with log file path.
        
        Args:
            log_path: Path to JSONL log file, supports ~ for home directory.
        """
        self._log_path = Path(log_path).expanduser()
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._current_session_id: Optional[str] = None
        self._last_event_id: Optional[str] = None

    def start_session(self) -> str:
        """Start a new session and return its UUID.
        
        Returns:
            Session ID as UUID v4 string.
        """
        session_id = str(uuid.uuid4())
        self._current_session_id = session_id
        self._last_event_id = None
        return session_id

    def emit(
        self,
        action: str,
        actor: str,
        agent_id: Optional[str] = None,
        payload: Optional[dict] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """Emit an event to the append-only log.
        
        Args:
            action: Action type string (e.g., "tool.call.completed").
            actor: Actor type, either "human" or "agent".
            agent_id: Agent ID, required when actor is "agent".
            payload: Event payload data, defaults to empty dict.
            tags: Metadata tags, defaults to empty list.
            
        Returns:
            Event ID as UUID v4 string.
        """
        if self._current_session_id is None:
            raise RuntimeError("No active session. Call start_session() first.")

        event_id = str(uuid.uuid4())
        timestamp = datetime.now(UTC).isoformat()
        
        event: dict = {
            "id": event_id,
            "timestamp": timestamp,
            "session_id": self._current_session_id,
            "causality_id": self._last_event_id,
            "actor": actor,
            "agent_id": agent_id,
            "action": action,
            "payload": payload if payload is not None else {},
            "integrity_hash": None,
            "metadata": {
                "source": "claw",
                "schema_version": "1.0",
                "tags": tags if tags is not None else [],
            },
        }

        # Calculate integrity hash (exclude integrity_hash field)
        event_for_hash = {k: v for k, v in event.items() if k != "integrity_hash"}
        # IMPORTANT: Use compact, sorted JSON to match HashChain.compute
        hash_input = json.dumps(event_for_hash, sort_keys=True, separators=(',', ':'))
        event["integrity_hash"] = hashlib.sha256(hash_input.encode()).hexdigest()

        # Append event to log file
        with open(self._log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        # MCP Instrumentation normalization (parasitic, non-breaking)
        try:
            from mcp_bridge import normalize_event
            normalized = normalize_event(event['action'], event['actor'], event['payload'], event_dict=event)
            event.update(normalized)
        except Exception as e:
            warnings.warn(f"MCP normalization failed: {e}")

        self._last_event_id = event_id
        return event_id

    def get_events(self, session_id: Optional[str] = None) -> list[dict]:
        """Retrieve events from the log, optionally filtered by session.
        
        Args:
            session_id: Session ID to filter by, or None for all events.
            
        Returns:
            List of event dictionaries.
        """
        events: list[dict] = []
        
        if not self._log_path.exists():
            return events

        with open(self._log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if session_id is None or event.get("session_id") == session_id:
                    events.append(event)

        return events