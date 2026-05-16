import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from hash_chain import HashChain


def _make_event(event_id: str, causality_id: str | None, action: str) -> dict:
    """Create an event with correct integrity_hash using HashChain.compute."""
    event: dict = {
        "id": event_id,
        "timestamp": "2025-01-01T00:00:00Z",
        "session_id": "test-session",
        "causality_id": causality_id,
        "actor": "agent",
        "agent_id": "r1",
        "action": action,
        "payload": {},
        "integrity_hash": None,
        "metadata": {"source": "claw", "schema_version": "1.0", "tags": []},
    }
    event["integrity_hash"] = HashChain.compute(event)
    return event


class TestHashChain(unittest.TestCase):

    def test_verify_valid_chain(self):
        """用正确事件构建链，verify 应返回 (True, OK)"""
        e1 = _make_event("id-1", None, "task.created")
        e2 = _make_event("id-2", "id-1", "tool.call.started")
        e3 = _make_event("id-3", "id-2", "tool.call.completed")

        ok, msg = HashChain.verify([e1, e2, e3])
        self.assertTrue(ok)
        self.assertEqual(msg, "OK")

    def test_verify_detects_hash_mismatch(self):
        """手动修改其中一个事件的 payload，verify 应检测出 hash 不匹配"""
        e1 = _make_event("id-1", None, "task.created")
        e2 = _make_event("id-2", "id-1", "tool.call.started")
        e3 = _make_event("id-3", "id-2", "tool.call.completed")

        e2["payload"] = {"tampered": True}

        ok, msg = HashChain.verify([e1, e2, e3])
        self.assertFalse(ok)
        self.assertIn("Hash mismatch", msg)
        self.assertIn("id-2", msg)

    def test_verify_detects_causality_broken(self):
        """手动修改其中一个事件的 causality_id 使其断裂，verify 应检测出链断裂"""
        e1 = _make_event("id-1", None, "task.created")
        e2 = _make_event("id-2", "id-1", "tool.call.started")
        e3 = _make_event("id-3", "id-2", "tool.call.completed")

        # 修改 causality_id 并重新计算 hash，使 hash 检查通过但因果链断裂
        e3["causality_id"] = "fake-id-000"
        e3["integrity_hash"] = HashChain.compute(e3)

        ok, msg = HashChain.verify([e1, e2, e3])
        self.assertFalse(ok)
        self.assertIn("Causality chain broken", msg)
        self.assertIn("id-3", msg)

    def test_compute_deterministic(self):
        """测试 compute 对同一事件多次计算应得到相同结果"""
        event = _make_event("id-1", None, "task.created")
        h1 = HashChain.compute(event)
        h2 = HashChain.compute(event)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)


if __name__ == "__main__":
    unittest.main()