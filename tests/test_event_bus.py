import unittest
import json
import os
import tempfile
from pathlib import Path
import sys

# 确保 src 目录在路径中
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from event_bus import EventBus


class TestEventBus(unittest.TestCase):

    def setUp(self):
        # 每个测试使用独立的临时日志文件
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "test_events.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_start_session_and_emit_produces_3_events(self):
        self.bus.start_session()
        e1 = self.bus.emit(action="task.created", actor="agent", agent_id="researcher")
        e2 = self.bus.emit(action="tool.call.started", actor="agent", agent_id="researcher")
        e3 = self.bus.emit(action="tool.call.completed", actor="agent", agent_id="researcher")

        events = self.bus.get_events()
        self.assertEqual(len(events), 3)

        # 检查每个事件都有必须的字段
        required_fields = ["id", "timestamp", "session_id", "causality_id",
                           "actor", "agent_id", "action", "payload",
                           "integrity_hash", "metadata"]
        for ev in events:
            for field in required_fields:
                self.assertIn(field, ev, f"Missing field {field}")

    def test_causality_chain(self):
        self.bus.start_session()
        id1 = self.bus.emit(action="task.created", actor="agent", agent_id="researcher")
        id2 = self.bus.emit(action="tool.call.started", actor="agent", agent_id="researcher")

        events = self.bus.get_events()
        self.assertEqual(events[1]["causality_id"], id1, "causality_id should point to previous event")

    def test_integrity_hash_present_and_64_chars(self):
        self.bus.start_session()
        self.bus.emit(action="task.created", actor="agent", agent_id="researcher")
        events = self.bus.get_events()
        h = events[0]["integrity_hash"]
        self.assertIsNotNone(h)
        self.assertEqual(len(h), 64, "SHA-256 hex should be 64 chars")

    def test_filter_by_session(self):
        sid1 = self.bus.start_session()
        self.bus.emit(action="task.created", actor="agent", agent_id="r1")
        sid2 = self.bus.start_session()
        self.bus.emit(action="task.created", actor="agent", agent_id="r2")

        self.assertEqual(len(self.bus.get_events(session_id=sid1)), 1)
        self.assertEqual(len(self.bus.get_events(session_id=sid2)), 1)


if __name__ == "__main__":
    unittest.main()