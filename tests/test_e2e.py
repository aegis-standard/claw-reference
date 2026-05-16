"""
端到端测试：Claw Reference Runtime 产生 AEF 证据 → 验证 → 回放
覆盖 EventBus、HashChain、ReplayVerifier 的完整协作
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


class TestEndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmpdir.name) / "evidence.jsonl"
        self.bus = EventBus(log_path=str(self.log_path))

    def tearDown(self):
        self.tmpdir.cleanup()

    def _generate_valid_session(self):
        """生成一组有效的工具调用事件"""
        self.bus.start_session()
        self.bus.emit(
            action="task.created",
            actor="agent",
            agent_id="researcher",
            payload={"goal": "搜索最新AI论文"}
        )
        self.bus.emit(
            action="tool.call.started",
            actor="agent",
            agent_id="researcher",
            payload={
                "tool_name": "search",
                "input": {"query": "AI agent 2025"}
            }
        )
        self.bus.emit(
            action="tool.call.completed",
            actor="agent",
            agent_id="researcher",
            payload={
                "tool_name": "search",
                "output": {"results": ["论文A", "论文B"], "count": 2}
            }
        )
        self.bus.emit(
            action="task.completed",
            actor="agent",
            agent_id="researcher",
            payload={"final_summary": "找到2篇相关论文"}
        )
        return self.bus.get_events()

    # ==================== 测试用例 ====================

    def test_full_happy_path(self):
        """完整正确流程：产生事件 → 哈希链验证 → 回放验证"""
        original = self._generate_valid_session()

        # 1. 哈希链验证
        ok, msg = HashChain.verify(original)
        self.assertTrue(ok, f"HashChain should pass on valid events: {msg}")

        # 2. 模拟回放（使用深拷贝作为回放事件）
        replayed = copy.deepcopy(original)

        # 3. 回放验证
        verifier = ReplayVerifier(original, replayed)
        result = verifier.verify()

        self.assertEqual(result["status"], "VALID",
                         f"Replay should be VALID: {result['details']}")
        self.assertTrue(result["conditions"]["event_order_preserved"])
        self.assertTrue(result["conditions"]["causality_chain_intact"])
        self.assertTrue(result["conditions"]["deterministic_match"])
        self.assertEqual(result["original_event_count"], 4)
        self.assertEqual(result["replayed_event_count"], 4)
        self.assertEqual(result["replay_runtime"], "claw-reference")

    def test_tampered_hash_detected(self):
        """篡改事件内容 → HashChain 检测失败"""
        original = self._generate_valid_session()
        # 篡改某个事件的 payload
        tampered = copy.deepcopy(original)
        tampered[1]["payload"]["input"]["query"] = "被篡改的查询"

        ok, msg = HashChain.verify(tampered)
        self.assertFalse(ok, "HashChain should detect tampering")
        self.assertIn("Hash mismatch", msg)

    def test_broken_causality_chain_detected(self):
        """断裂因果链 → HashChain 检测失败"""
        original = self._generate_valid_session()
        broken = copy.deepcopy(original)
        # 将第3个事件的 causality_id 改为一个不存在的 id
        broken[2]["causality_id"] = "nonexistent-id"
        # 重新计算所有事件的哈希，因为内容已变
        for event in broken:
            event["integrity_hash"] = HashChain.compute(event)

        ok, msg = HashChain.verify(broken)
        self.assertFalse(ok, "HashChain should detect broken chain")
        self.assertIn("Causality chain broken", msg)

    def test_replay_invalid_event_order(self):
        """回放事件顺序不同 → INVALID"""
        original = self._generate_valid_session()
        replayed = copy.deepcopy(original)
        # 交换第2和第3个事件
        replayed[1], replayed[2] = replayed[2], replayed[1]

        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["event_order_preserved"])

    def test_replay_invalid_tool_output(self):
        """回放中工具输出不同 → INVALID"""
        original = self._generate_valid_session()
        replayed = copy.deepcopy(original)
        # 修改 tool.call.completed 的 output
        replayed[2]["payload"]["output"]["count"] = 99

        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["deterministic_match"])

    def test_replay_empty_events(self):
        """空事件列表 → 应返回 VALID"""
        result = ReplayVerifier([], []).verify()
        self.assertEqual(result["status"], "VALID")
        self.assertEqual(result["original_event_count"], 0)

    def test_replay_missing_event(self):
        """回放事件缺少一个 → INVALID"""
        original = self._generate_valid_session()
        replayed = copy.deepcopy(original)[:3]  # 删除最后一个事件

        result = ReplayVerifier(original, replayed).verify()
        self.assertEqual(result["status"], "INVALID")
        self.assertFalse(result["conditions"]["event_order_preserved"])


if __name__ == "__main__":
    unittest.main()