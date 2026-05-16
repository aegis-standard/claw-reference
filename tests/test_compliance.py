"""
Claw Reference Runtime — AEF Compliance Suite 初步验证
验证 Claw 产生的事件是否符合 AEF RFC-0001 / RFC-0002 / RFC-0006 (L4)
"""
import unittest
import tempfile
import copy
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from event_bus import EventBus
from hash_chain import HashChain
from replay_verifier import ReplayVerifier


class TestCompliance(unittest.TestCase):

    REQUIRED_FIELDS = [
        "id", "timestamp", "session_id", "causality_id",
        "actor", "agent_id", "action", "payload",
        "integrity_hash", "metadata"
    ]

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "evidence.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _generate_session(self, n_tool_calls=3):
        """生成包含 n 个工具调用的完整会话"""
        self.bus.start_session()
        self.bus.emit(action="task.created", actor="agent", agent_id="researcher",
                      payload={"goal": "compliance test"})
        for i in range(n_tool_calls):
            self.bus.emit(action="tool.call.started", actor="agent", agent_id="researcher",
                          payload={"tool_name": f"tool_{i}", "input": {"value": i}})
            self.bus.emit(action="tool.call.completed", actor="agent", agent_id="researcher",
                          payload={"tool_name": f"tool_{i}", "output": {"result": i * 2}})
        self.bus.emit(action="task.completed", actor="agent", agent_id="researcher",
                      payload={"final_summary": "ok"})
        return self.bus.get_events()

    # ==================== RFC-0001: Event Core Schema ====================

    def test_rfc0001_all_required_fields_present(self):
        events = self._generate_session(1)
        for event in events:
            for field in self.REQUIRED_FIELDS:
                self.assertIn(field, event, f"Missing required field: {field}")

    def test_rfc0001_field_types(self):
        events = self._generate_session(1)
        for event in events:
            self.assertIsInstance(event["id"], str)
            self.assertIsInstance(event["timestamp"], str)
            self.assertIsInstance(event["session_id"], str)
            self.assertIsInstance(event["payload"], dict)
            self.assertIsInstance(event["metadata"], dict)

    def test_rfc0001_actor_values(self):
        events = self._generate_session(1)
        for event in events:
            self.assertIn(event["actor"], ["human", "agent"])

    def test_rfc0001_first_event_causality_null(self):
        events = self._generate_session(1)
        self.assertIsNone(events[0]["causality_id"])

    # ==================== RFC-0002: Replay Semantics ====================

    def test_rfc0002_event_order_preserved(self):
        original = self._generate_session(2)
        replayed = copy.deepcopy(original)
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertTrue(result["conditions"]["event_order_preserved"])

    def test_rfc0002_causality_chain_intact(self):
        original = self._generate_session(2)
        ok, msg = HashChain.verify(original)
        self.assertTrue(ok, f"Causality chain should be intact: {msg}")

    def test_rfc0002_deterministic_component_match(self):
        original = self._generate_session(2)
        replayed = copy.deepcopy(original)
        result = ReplayVerifier(original, replayed).verify()
        self.assertTrue(result["conditions"]["deterministic_match"])

    def test_rfc0002_invalid_event_order_detected(self):
        """事件顺序不同 → INVALID"""
        original = self._generate_session(3)  # 多生成几个事件，使 action 序列多样
        replayed = copy.deepcopy(original)
        # 将最后一个事件移到最前面，必然破坏顺序
        replayed = [replayed[-1]] + replayed[:-1]
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["event_order_preserved"])

    # ==================== RFC-0006: Determinism (L4) ====================

    def test_rfc0006_hash_integrity(self):
        events = self._generate_session(3)
        ok, msg = HashChain.verify(events)
        self.assertTrue(ok, f"Hash integrity failed: {msg}")

    def test_rfc0006_replay_hash_identical(self):
        original = self._generate_session(2)
        replayed = copy.deepcopy(original)
        for orig, repl in zip(original, replayed):
            self.assertEqual(orig["integrity_hash"], repl["integrity_hash"])

    def test_rfc0006_float_tolerance(self):
        original = self._generate_session(1)
        replayed = copy.deepcopy(original)
        for event in replayed:
            if event["action"] == "tool.call.completed":
                event["payload"]["output"]["result"] = 1.0000005
        for event in original:
            if event["action"] == "tool.call.completed":
                event["payload"]["output"]["result"] = 1.0000001
        result = ReplayVerifier(original, replayed).verify()
        self.assertTrue(result["conditions"]["deterministic_match"])

    # ==================== 综合 ====================

    def test_full_session_l4_compliance(self):
        original = self._generate_session(5)
        replayed = copy.deepcopy(original)
        ok, msg = HashChain.verify(original)
        self.assertTrue(ok, f"Original hash chain failed: {msg}")
        ok, msg = HashChain.verify(replayed)
        self.assertTrue(ok, f"Replay hash chain failed: {msg}")
        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["replay_runtime"], "claw-reference")


if __name__ == "__main__":
    unittest.main()