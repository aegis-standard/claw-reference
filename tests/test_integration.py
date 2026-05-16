"""Integration tests for EventBus, HashChain, ReplayVerifier, InterruptHandler, HumanOverrideHandler."""

import copy
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from event_bus import EventBus
from hash_chain import HashChain
from replay_verifier import ReplayVerifier
from interrupt import InterruptHandler
from human_override import HumanOverrideHandler


class TestIntegration(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "test.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))
        self.bus.start_session()
        self.interrupt = InterruptHandler(self.bus)
        self.override = HumanOverrideHandler(self.bus)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _emit(self, action: str, actor: str = "agent", agent_id: str = "r1",
              payload: dict | None = None) -> str:
        eid = self.bus.emit(action=action, actor=actor, agent_id=agent_id,
                            payload=payload or {})
        self.interrupt.update_last_success_event_id(eid)
        return eid

    def test_full_workflow_with_interrupt(self):
        """完整工作流：task → tool → interrupt → override → resolve → task"""
        self._emit("task.created")
        self._emit("tool.call.started", payload={"input": "x"})
        self._emit("tool.call.completed", payload={"output": "y"})

        self.interrupt.interrupt(reason="human_request", source="human")
        self.override.override(original_output="y", corrected_output="z",
                               reason="factual_error")
        self.interrupt.resolve()

        self._emit("task.completed")

        events = self.bus.get_events()
        ok, msg = HashChain.verify(events)
        self.assertTrue(ok, f"HashChain.verify failed: {msg}")

        result = ReplayVerifier(events, copy.deepcopy(events)).verify()
        self.assertEqual(result["status"], "VALID")

    def test_interrupt_during_tool_call(self):
        """工具调用期间中断：started → interrupt → error → resolve"""
        self._emit("tool.call.started", payload={"input": "x"})
        self.interrupt.interrupt(reason="timeout", source="system")
        self._emit("tool.call.error", payload={"error": "timeout"})
        self.interrupt.resolve()

        events = self.bus.get_events()
        self.assertEqual(events[1]["action"], "agent.interrupted")
        self.assertEqual(events[1]["payload"]["reason"], "timeout")
        self.assertEqual(events[2]["action"], "tool.call.error")
        self.assertEqual(events[3]["action"], "agent.interrupt.resolved")
        # resolved causality_id points to the last event before resolve (tool.call.error)
        self.assertEqual(events[3]["causality_id"], events[2]["id"])

    def test_override_without_interrupt(self):
        """仅覆盖不中断：completed → override"""
        e1 = self._emit("tool.call.completed", payload={"output": "original"})
        self.override.override(original_output="original", corrected_output="corrected",
                               reason="direction_deviation", related_event_id=e1)

        events = self.bus.get_events()
        self.assertEqual(events[1]["action"], "human.override")
        self.assertEqual(events[1]["causality_id"], e1)
        self.assertEqual(events[1]["payload"]["corrected_output"], "corrected")

    def test_override_chain_with_interrupt(self):
        """覆盖链与中断交替：override → override → interrupt → resolve"""
        self._emit("tool.call.completed", payload={"output": "v0"})
        self.override.override(original_output="v0", corrected_output="v1", reason="fix1")
        self.override.override(original_output="", corrected_output="v2", reason="fix2")
        self.interrupt.interrupt(reason="human_request", source="human")
        self.interrupt.resolve()

        events = self.bus.get_events()
        self.assertEqual(events[2]["payload"]["original_output"], "v1")
        self.assertEqual(events[2]["payload"]["corrected_output"], "v2")
        self.assertEqual(events[3]["action"], "agent.interrupted")
        self.assertEqual(events[4]["action"], "agent.interrupt.resolved")

    def test_l4_compliance_after_interrupt(self):
        """中断后 L4 合规：HashChain.verify 通过，ReplayVerifier 返回 VALID"""
        self._emit("task.created")
        self._emit("tool.call.started", payload={"input": "a"})
        self.interrupt.interrupt(reason="timeout", source="system")
        self._emit("tool.call.error", payload={"error": "timeout"})
        self.interrupt.resolve()
        self._emit("task.completed")

        events = self.bus.get_events()
        ok, msg = HashChain.verify(events)
        self.assertTrue(ok, f"HashChain.verify failed: {msg}")

        result = ReplayVerifier(events, copy.deepcopy(events)).verify()
        self.assertEqual(result["status"], "VALID")

    def test_l4_compliance_after_override(self):
        """覆盖后 L4 合规：HashChain.verify 通过，ReplayVerifier 返回 VALID"""
        self._emit("task.created")
        self._emit("tool.call.started", payload={"input": "a"})
        e3 = self._emit("tool.call.completed", payload={"output": "b"})
        self.override.override(original_output="b", corrected_output="c",
                               reason="correction", related_event_id=e3)
        self._emit("task.completed")

        events = self.bus.get_events()
        ok, msg = HashChain.verify(events)
        self.assertTrue(ok, f"HashChain.verify failed: {msg}")

        result = ReplayVerifier(events, copy.deepcopy(events)).verify()
        self.assertEqual(result["status"], "VALID")


if __name__ == "__main__":
    unittest.main()