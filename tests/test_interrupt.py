import unittest
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from event_bus import EventBus
from interrupt import InterruptHandler


class TestInterruptHandler(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "test.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))
        self.bus.start_session()
        self.handler = InterruptHandler(self.bus)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_interrupt_and_resolve(self):
        """正常中断和恢复流程，验证事件序列"""
        e1 = self.bus.emit(action="task.created", actor="agent", agent_id="r1")
        self.handler.update_last_success_event_id(e1)

        int_id = self.handler.interrupt(reason="timeout", source="system")
        self.assertTrue(self.handler.is_interrupted())

        res_id = self.handler.resolve()
        self.assertFalse(self.handler.is_interrupted())

        events = self.bus.get_events()
        self.assertEqual(len(events), 3)
        self.assertEqual(events[1]["action"], "agent.interrupted")
        self.assertEqual(events[1]["payload"]["reason"], "timeout")
        self.assertEqual(events[1]["payload"]["source"], "system")
        self.assertEqual(events[1]["causality_id"], e1)
        self.assertEqual(events[2]["action"], "agent.interrupt.resolved")
        self.assertEqual(events[2]["payload"]["resumed_from_event_id"], int_id)
        self.assertEqual(events[2]["causality_id"], int_id)

    def test_interrupt_state_toggle(self):
        """中断状态翻转"""
        self.assertFalse(self.handler.is_interrupted())
        self.handler.interrupt(reason="timeout")
        self.assertTrue(self.handler.is_interrupted())
        self.handler.resolve()
        self.assertFalse(self.handler.is_interrupted())

    def test_resolve_when_not_interrupted_raises(self):
        """未中断时调用 resolve 应抛出异常"""
        with self.assertRaises(RuntimeError):
            self.handler.resolve()

    def test_nested_interrupt_rejected(self):
        """嵌套中断应被拒绝"""
        self.handler.interrupt(reason="timeout", source="system")
        with self.assertRaises(RuntimeError):
            self.handler.interrupt(reason="human_request", source="human")

    def test_causality_after_resolve(self):
        """中断后恢复，下一个事件的 causality_id 应指向 agent.interrupt.resolved"""
        e1 = self.bus.emit(action="task.created", actor="agent", agent_id="r1")
        self.handler.update_last_success_event_id(e1)

        self.handler.interrupt(reason="timeout")
        res_id = self.handler.resolve()

        e2 = self.bus.emit(action="task.continued", actor="agent", agent_id="r1")
        events = self.bus.get_events()
        self.assertEqual(events[-1]["causality_id"], res_id)

    def test_get_last_success_event_id(self):
        """get_last_success_event_id 返回中断前最后一个成功事件 id"""
        e1 = self.bus.emit(action="task.created", actor="agent", agent_id="r1")
        self.handler.update_last_success_event_id(e1)
        self.assertEqual(self.handler.get_last_success_event_id(), e1)

    def test_get_last_success_event_id_before_any_event_raises(self):
        """未记录任何成功事件时调用 get_last_success_event_id 应抛出异常"""
        with self.assertRaises(RuntimeError):
            self.handler.get_last_success_event_id()

    def test_invalid_source_raises(self):
        """无效的 source 应抛出 ValueError"""
        with self.assertRaises(ValueError):
            self.handler.interrupt(reason="timeout", source="invalid")

    def test_default_source_is_system(self):
        """默认 source 为 system"""
        self.handler.interrupt(reason="timeout")
        events = self.bus.get_events()
        self.assertEqual(events[0]["payload"]["source"], "system")


if __name__ == "__main__":
    unittest.main()
