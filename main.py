"""
Claw Reference Runtime CLI — AEF 证据产生与查看
用法:
  python main.py                 进入交互模式（推荐）
  python main.py test            运行自检
  python main.py help            显示帮助

交互模式命令:
  help         显示命令列表
  session      启动新会话（自动结束之前会话）
  interrupt [reason]  触发中断
  override [reason]   触发覆盖
  resume       恢复中断
  log          查看当前会话事件日志
  verify       验证当前会话哈希链和回放
  test         运行自检
  exit / quit  退出
"""

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent / "src"))

from event_bus import EventBus
from interrupt import InterruptHandler
from human_override import HumanOverrideHandler
from hash_chain import HashChain
from replay_verifier import ReplayVerifier

LOG_PATH = str(Path.home() / ".claw" / "evidence.jsonl")

# 全局组件
bus = EventBus(log_path=LOG_PATH)
interrupt_handler = InterruptHandler(bus)
override_handler = HumanOverrideHandler(bus)
current_session_id: Optional[str] = None


def print_help():
    print(__doc__)


def cmd_session():
    """启动新会话并运行演示工作流"""
    global current_session_id, interrupt_handler, override_handler

    # 如果已有活动会话，新会话之前重置中断/覆盖状态
    if current_session_id:
        print(f"结束旧会话 {current_session_id[:8]}...，启动新会话。")
        # 重置处理器（简单重建实例）
        interrupt_handler = InterruptHandler(bus)
        override_handler = HumanOverrideHandler(bus)

    sid = bus.start_session()
    current_session_id = sid
    print(f"会话已启动: {sid}")

    eid = bus.emit("task.created", "agent", "researcher", {"goal": "Claw 演示"})
    interrupt_handler.update_last_success_event_id(eid)
    print(f"  ✓ task.created ({eid[:8]}...)")

    eid = bus.emit("tool.call.started", "agent", "researcher",
                   {"tool_name": "search", "input": {"query": "AI agent 2026"}})
    interrupt_handler.update_last_success_event_id(eid)
    print(f"  ✓ tool.call.started ({eid[:8]}...)")

    eid = bus.emit("tool.call.completed", "agent", "researcher",
                   {"tool_name": "search", "output": {"results": ["论文A", "论文B"], "count": 2}})
    interrupt_handler.update_last_success_event_id(eid)
    print(f"  ✓ tool.call.completed ({eid[:8]}...)")

    eid = bus.emit("task.completed", "agent", "researcher",
                   {"final_summary": "找到2篇相关论文"})
    interrupt_handler.update_last_success_event_id(eid)
    print(f"  ✓ task.completed ({eid[:8]}...)\n")


def cmd_interrupt(reason="human_request"):
    if current_session_id is None:
        print("❌ 没有活动会话。请先运行 session。")
        return
    if interrupt_handler.is_interrupted():
        print("⚠️ 已经处于中断状态。")
        return
    try:
        eid = interrupt_handler.interrupt(reason=reason, source="human")
        print(f"中断已触发: {eid[:8]}... (原因: {reason})")
    except RuntimeError as e:
        print(f"❌ 错误: {e}")


def cmd_resume():
    if current_session_id is None:
        print("❌ 没有活动会话。请先运行 session。")
        return
    if not interrupt_handler.is_interrupted():
        print("⚠️ 当前未处于中断状态。")
        return
    try:
        eid = interrupt_handler.resolve()
        print(f"中断已恢复: {eid[:8]}...")
    except RuntimeError as e:
        print(f"❌ 错误: {e}")


def cmd_override(reason="方向偏离"):
    if current_session_id is None:
        print("❌ 没有活动会话。请先运行 session。")
        return
    try:
        last_id = interrupt_handler.get_last_success_event_id()
    except RuntimeError:
        print("❌ 没有可覆盖的事件。请先运行 session。")
        return

    original = "（演示用原始输出）"
    corrected = "（演示用修正后输出）"
    eid = override_handler.override(original_output=original,
                                    corrected_output=corrected,
                                    reason=reason,
                                    related_event_id=last_id,
                                    scope="full")
    print(f"覆盖已记录: {eid[:8]}... (原因: {reason})")


def cmd_log():
    if current_session_id is None:
        print("📭 没有活动会话。请先运行 session。")
        return
    events = bus.get_events(session_id=current_session_id)
    if not events:
        print("当前会话没有事件。")
        return
    print(f"会话 {current_session_id[:8]} 共 {len(events)} 个事件:\n")
    for ev in events:
        print(f"  {ev['id'][:8]}... | {ev['action']:30s} | actor={ev['actor']} | hash={ev['integrity_hash'][:12]}...")


def cmd_verify():
    if current_session_id is None:
        print("📭 没有活动会话。请先运行 session。")
        return
    events = bus.get_events(session_id=current_session_id)
    if not events:
        print("当前会话没有事件可验证。")
        return
    ok, msg = HashChain.verify(events)
    if ok:
        print("✅ 哈希链完整性验证通过")
    else:
        print(f"❌ 哈希链验证失败: {msg}")

    import copy
    replay = copy.deepcopy(events)
    result = ReplayVerifier(events, replay).verify()
    if result["status"] == "VALID":
        print("✅ 回放验证通过 (VALID)")
    else:
        print(f"❌ 回放验证失败: {result['details']['mismatch_description']}")


def cmd_test():
    print("运行自检...")
    import tempfile
    tmp = tempfile.TemporaryDirectory()
    test_bus = EventBus(log_path=str(Path(tmp.name) / "test.jsonl"))
    ih = InterruptHandler(test_bus)
    oh = HumanOverrideHandler(test_bus)

    test_bus.start_session()
    eid = test_bus.emit("task.created", "agent", "researcher", {"goal": "自检"})
    ih.update_last_success_event_id(eid)
    eid = test_bus.emit("tool.call.started", "agent", "researcher", {"tool_name": "check", "input": {}})
    ih.update_last_success_event_id(eid)
    eid = test_bus.emit("tool.call.completed", "agent", "researcher",
                         {"tool_name": "check", "output": {"status": "ok"}})
    ih.update_last_success_event_id(eid)
    eid = test_bus.emit("task.completed", "agent", "researcher", {"final_summary": "自检通过"})
    ih.update_last_success_event_id(eid)

    events = test_bus.get_events()
    ok, msg = HashChain.verify(events)
    if ok:
        print("✅ 自检哈希链通过")
    else:
        print(f"❌ 自检哈希链失败: {msg}")
        tmp.cleanup()
        return

    import copy
    replay = copy.deepcopy(events)
    result = ReplayVerifier(events, replay).verify()
    if result["status"] == "VALID":
        print("✅ 自检回放通过 (L4 合规)")
    else:
        print(f"❌ 自检回放失败: {result['details']}")
    tmp.cleanup()


def interactive_loop():
    # Check MCP Instrumentation availability
    try:
        from mcp_bridge import normalize_event
        print("MCP Instrumentation ENABLED")
    except Exception:
        print("MCP Instrumentation UNAVAILABLE")

    print("Claw Interactive Shell (输入 help 查看命令，当前会话: 无)")
    while True:
        try:
            prompt = f"claw [{current_session_id[:8] if current_session_id else 'no session'}]> "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n退出。")
            break
        if not line:
            continue
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else None

        if cmd in ("exit", "quit"):
            break
        elif cmd == "help":
            print("命令: session, log, verify, interrupt [reason], override [reason], resume, test, exit")
        elif cmd == "session":
            cmd_session()
        elif cmd == "log":
            cmd_log()
        elif cmd == "verify":
            cmd_verify()
        elif cmd == "interrupt":
            cmd_interrupt(reason=arg or "human_request")
        elif cmd == "override":
            cmd_override(reason=arg or "方向偏离")
        elif cmd == "resume":
            cmd_resume()
        elif cmd == "test":
            cmd_test()
        else:
            print(f"未知命令: {cmd}")


def main():
    # Check MCP Instrumentation availability (for non-interactive mode)
    try:
        from mcp_bridge import normalize_event
        print("MCP Instrumentation ENABLED")
    except Exception:
        print("MCP Instrumentation UNAVAILABLE")

    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "test":
            cmd_test()
        elif cmd in ("help", "--help", "-h"):
            print_help()
        else:
            print(f"未知命令: {cmd}")
            print_help()
    else:
        interactive_loop()


if __name__ == "__main__":
    main()