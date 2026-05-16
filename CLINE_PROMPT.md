# Claw Reference Runtime — 最小可运行内核

## 项目背景

Claw 是 AEGIS AEF 协议的参考实现 (Reference Runtime)。它是一个本地优先、可审计、可回放的 AI Agent 执行黑匣子。

Claw 的唯一职责是：**产生符合 AEF 标准的、不可篡改的执行证据**。

Claw 必须通过 AEF Compliance Suite L4 认证。

## 宪法纪律

以下规则不可违反：
1. 所有输出事件必须符合 AEF RFC-0001 (Event Core Schema)
2. 事件日志 append-only，物理不可修改或删除
3. 每个事件自动计算 integrity_hash，并与前一个事件形成哈希链
4. 提供 replay 验证工具，能检测任何事件篡改
5. 单文件不超过 200 行

## 任务

实现以下三个模块：

### 1. EventBus (`src/event_bus.py`)

产生符合 AEF RFC-0001 的事件，并写入 append-only 日志。

```python
class EventBus:
    def __init__(self, log_path: str = "~/.claw/evidence.jsonl")
    def start_session(self) -> str  # 返回 session_id
    def emit(self, action: str, actor: str, agent_id: str = None, 
             payload: dict = None, tags: list[str] = None) -> str  # 返回 event_id
    def get_events(self, session_id: str = None) -> list[dict]

    要求：

写入 ~/.claw/evidence.jsonl，追加模式

自动生成 UUID id、ISO8601 timestamp、session_id

自动计算 causality_id（上一条事件的 id）

自动计算 integrity_hash = SHA-256(除 hash 外的所有字段 JSON)

支持通过 session_id 过滤读取

2. HashChain (src/hash_chain.py)
python
class HashChain:
    @staticmethod
    def compute(event: dict) -> str  # 返回 SHA-256 hex
    @staticmethod
    def verify(events: list[dict]) -> tuple[bool, str]  # (是否完整, 错误信息)
要求：

compute：排除 integrity_hash 字段后计算 JSON 的 SHA-256

verify：遍历事件列表，检测每个事件的 hash 是否正确，检测 causality_id 链是否连续

任何 hash 不匹配或链断裂，返回 (False, 错误描述)

3. ReplayVerifier (src/replay_verifier.py)
按照 AEF RFC-0002 验证回放合法性。

python
class ReplayVerifier:
    def __init__(self, original_events: list[dict], replayed_events: list[dict])
    def verify(self) -> dict  # 返回 replay_result 对象（符合 RFC-0002 第4节）
要求：

验证 3.1 Event Order Preserved：逐事件比对 action 序列

验证 3.2 Causality Chain Intact：因果链无环、无断裂

验证 3.3 Deterministic Component Match：工具调用的 input/output 匹配（字符串精确，数字容差 1e-6）

返回完整的 replay_result 结构（含 session_id, status, conditions, details）

测试
在 tests/ 下创建 test_all.py：

测试 EventBus 产生的事件格式符合 RFC-0001

测试 HashChain verify 能检测篡改

测试 ReplayVerifier 正确判定 VALID 和 INVALID 场景

提供至少 3 个事件的有效事件流和 1 个被篡改的事件流

技术约束
Python 3.10+

仅依赖标准库 (json, uuid, hashlib, datetime, pathlib)

类型标注完整

每个模块不超过 150 行

所有路径使用 pathlib.Path

成功标准
运行 python tests/test_all.py 全部通过

EventBus 产生的事件可被 AEF Validator 接受

HashChain.verify 能准确检测任何字段的篡改

ReplayVerifier.verify 输出完全符合 RFC-0002 第 4 节的 replay_result 结构