"""HashChain module for event integrity verification."""

import copy
import hashlib
import json


class HashChain:
    """Hash chain for verifying event integrity and causality."""

    @staticmethod
    def compute(event: dict) -> str:
        """计算事件的完整性哈希，返回 SHA-256 hex 字符串"""
        event_copy = copy.deepcopy(event)
        event_copy.pop("integrity_hash", None)
        # Same serialization as EventBus: compact, sorted keys
        hash_input = json.dumps(event_copy, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(hash_input.encode()).hexdigest()

    @staticmethod
    def verify(events: list[dict]) -> tuple[bool, str]:
        """验证事件列表的完整性，返回 (是否通过, 错误信息)"""
        if not events:
            return (True, "OK")

        for i, event in enumerate(events):
            event_id = event.get("id", "unknown")

            # 1. Verify hash integrity
            computed_hash = HashChain.compute(event)
            stored_hash = event.get("integrity_hash")
            if computed_hash != stored_hash:
                return (False, f"Hash mismatch at event {event_id}")

            # 2. Verify causality chain (except first event)
            if i > 0:
                prev_id = events[i - 1].get("id")
                curr_causality_id = event.get("causality_id")
                if curr_causality_id != prev_id:
                    return (False, f"Causality chain broken at event {event_id}")

        return (True, "OK")