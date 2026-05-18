"""MCP Bridge — 安全加载 AEF MCP Instrumentation Layer."""

import hashlib
import warnings
from typing import Optional

try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(r"D:\AEGISaef-core")))
    from mcp.server import AEFInstrumentor
    _MCP_AVAILABLE = True
except ImportError:
    _MCP_AVAILABLE = False


def normalize_event(
    action: str,
    actor: str,
    payload: dict,
    event_dict: Optional[dict] = None,
) -> dict:
    """标准化事件，优先使用 AEF MCP，否则降级为基本哈希。"""
    if _MCP_AVAILABLE:
        try:
            instrumentor = AEFInstrumentor()
            return instrumentor.aef_normalize(action, actor, payload, event_dict)
        except Exception as e:
            warnings.warn(f"AEF MCP normalization failed: {e}")

    # 降级：返回基本字段 + 哈希
    raw = f"{action}:{actor}:{payload}"
    fallback_hash = hashlib.sha256(raw.encode()).hexdigest()
    return {
        "mcp_normalized": False,
        "mcp_fallback_hash": fallback_hash,
    }