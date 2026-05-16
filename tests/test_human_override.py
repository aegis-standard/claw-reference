import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from event_bus import EventBus
from human_override import HumanOverrideHandler


class TestHumanOverrideHandler(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "test.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))
        self.bus.start_session()
        self.handler = HumanOverrideHandler(self.bus)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_basic_override(self):
        """基本覆盖流程，验证事件字段"""
        e1 = self.bus.emit(action="tool.call.completed", actor="agent", agent_id="r1",
                           payload={"output": "original"})
        ov_id = self.handler.override(
            original_output="original",
            corrected_output="corrected",
            reason="factual_error",
            related_event_id=e1,
        )

        events = self.bus.get_events()
        self.assertEqual(len(events), 2)
        ev = events[1]
        self.assertEqual(ev["action"], "human.override")
        self.assertEqual(ev["actor"], "human")
        self.assertIsNone(ev["agent_id"])
        self.assertEqual(ev["payload"]["original_output"], "original")
        self.assertEqual(ev["payload"]["corrected_output"], "corrected")
        self.assertEqual(ev["payload"]["override_reason"], "factual_error")
        self.assertEqual(ev["payload"]["related_event_id"], e1)

    def test_override_causality_points_to_related_event(self):
        """覆盖的 causality_id 指向相关事件"""
        e1 = self.bus.emit(action="tool.call.completed", actor="agent", agent_id="r1",
                           payload={"output": "original"})
        self.handler.override(
            original_output="original",
            corrected_output="corrected",
            reason="test",
            related_event_id=e1,
        )
        events = self.bus.get_events()
        self.assertEqual(events[1]["causality_id"], e1)

    def test_override_chain(self):
        """两次覆盖，第二次的 original_output 自动为第一次的 corrected_output"""
        e1 = self.bus.emit(action="tool.call.completed", actor="agent", agent_id="r1",
                           payload={"output": "v0"})
        self.handler.override(original_output="v0", corrected_output="v1", reason="fix1")
        self.handler.override(original_output="", corrected_output="v2", reason="fix2")

        events = self.bus.get_events()
        self.assertEqual(events[2]["payload"]["original_output"], "v1")
        self.assertEqual(events[2]["payload"]["corrected_output"], "v2")

    def test_get_last_override(self):
        """get_last_override 返回正确内容"""
        self.assertIsNone(self.handler.get_last_override())
        self.handler.override(original_output="a", corrected_output="b", reason="r")
        last = self.handler.get_last_override()
        self.assertEqual(last["corrected_output"], "b")
        self.assertEqual(last["reason"], "r")

    def test_is_overridden(self):
        """is_overridden 状态正确"""
        self.assertFalse(self.handler.is_overridden())
        self.handler.override(original_output="a", corrected_output="b", reason="r")
        self.assertTrue(self.handler.is_overridden())

    def test_override_scope_default_full(self):
        """override_scope 默认值为 full"""
        self.handler.override(original_output="a", corrected_output="b", reason="r")
        events = self.bus.get_events()
        self.assertEqual(events[0]["payload"]["override_scope"], "full")

    def test_override_scope_partial(self):
        """override_scope 可设为 partial"""
        self.handler.override(original_output="a", corrected_output="b", reason="r", scope="partial")
        events = self.bus.get_events()
        self.assertEqual(events[0]["payload"]["override_scope"], "partial")

    def test_invalid_scope_raises(self):
        """无效 scope 应抛出 ValueError"""
        with self.assertRaises(ValueError):
            self.handler.override(original_output="a", corrected_output="b", reason="r", scope="invalid")


if __name__ == "__main__":
    unittest.main()