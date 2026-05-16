import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from replay_verifier import ReplayVerifier


def _make_event(event_id: str, causality_id: str | None, action: str,
                payload: dict | None = None) -> dict:
    return {
        "id": event_id,
        "timestamp": "2025-01-01T00:00:00Z",
        "session_id": "test-session",
        "causality_id": causality_id,
        "actor": "agent",
        "agent_id": "r1",
        "action": action,
        "payload": payload or {},
        "integrity_hash": "fake",
        "metadata": {},
    }


class TestReplayVerifier(unittest.TestCase):

    def test_valid_replay(self):
        """相同事件作为回放，verify 应返回 VALID"""
        events = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started", {"input": "x"}),
            _make_event("id-3", "id-2", "tool.call.completed", {"output": "y"}),
        ]
        result = ReplayVerifier(events, events).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertTrue(result["conditions"]["event_order_preserved"])
        self.assertTrue(result["conditions"]["causality_chain_intact"])
        self.assertTrue(result["conditions"]["deterministic_match"])

    def test_deterministic_mismatch_output(self):
        """修改回放事件中 tool.call.completed 的 output，应返回 INVALID"""
        original = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started", {"input": "x"}),
            _make_event("id-3", "id-2", "tool.call.completed", {"output": "original"}),
        ]
        replayed = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started", {"input": "x"}),
            _make_event("id-3", "id-2", "tool.call.completed", {"output": "tampered"}),
        ]
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["deterministic_match"])

    def test_event_order_mismatch(self):
        """交换两个事件顺序，应返回 INVALID"""
        original = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started"),
            _make_event("id-3", "id-2", "tool.call.completed"),
        ]
        replayed = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-3", "id-2", "tool.call.completed"),
            _make_event("id-2", "id-1", "tool.call.started"),
        ]
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["event_order_preserved"])

    def test_causality_chain_broken(self):
        """修改回放事件中 causality_id 使其断裂，应返回 INVALID"""
        original = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started"),
            _make_event("id-3", "id-2", "tool.call.completed"),
        ]
        replayed = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started"),
            _make_event("id-3", "fake-id", "tool.call.completed"),
        ]
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["causality_chain_intact"])

    def test_float_tolerance(self):
        """浮点数容差：差异 1e-7 ≤ 1e-6 应视为匹配"""
        original = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started", {"input": 1.0000001}),
        ]
        replayed = [
            _make_event("id-1", None, "task.created"),
            _make_event("id-2", "id-1", "tool.call.started", {"input": 1.0000002}),
        ]
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertTrue(result["conditions"]["deterministic_match"])

    def test_empty_events(self):
        """空事件列表的情况"""
        result = ReplayVerifier([], []).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["original_event_count"], 0)
        self.assertEqual(result["replayed_event_count"], 0)


if __name__ == "__main__":
    unittest.main()