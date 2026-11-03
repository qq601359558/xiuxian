# F17 LLM 超时可配置 — Spec

## 一、问题（解构本质）
真 AI 实测（2026-11-03）发现：`ai/gateway.py::_chat_json` 写死超时 20s，对慢中转
（New API relay，延迟接近 20s）偏紧，重提示经常超时降级本地模板。运营侧无法在不改
代码的情况下调大超时。总纲 F17 定死口径：超时改为 config 常量 + .env 可调
（`LLM_TIMEOUT_SECONDS`，默认 30）。

## 二、行为契约
1. 新增配置 `LLM_TIMEOUT_SECONDS`：在 `config.py` 的 AI 模型接口配置段单点读取
   （`os.getenv`，与 `LLM_API_BASE/LLM_MODEL` 完全同口径，模块导入时冻结），
   解析函数 `_llm_timeout_seconds()` 口径：
   - 未设置 → 30.0；
   - 可解析为有限浮点数 → 钳制到 [5.0, 120.0]；
   - 非法值（非数字、NaN、±Inf、空串）→ 回退 30.0。
2. 主聊天通道默认值统一读该常量（函数签名默认参数在导入时绑定，与既有
   config 常量作默认值的模式一致）：
   - `ai/gateway.py::_chat_json` 默认 20.0 → `LLM_TIMEOUT_SECONDS`；
   - `ai/gateway.py::_chat_text` 默认 8.0 → `LLM_TIMEOUT_SECONDS`；
   - `ai/gateway.py::_router_data` 默认 20.0 → `LLM_TIMEOUT_SECONDS`；
   - `ai/router.py::invoke` 默认 20.0 → `LLM_TIMEOUT_SECONDS`。
3. 唯一有意行为变化：未设置 env 时，主通道默认超时由 20s（_chat_text 为 8s）
   变为 30s。除超时数值外，重试/降级/解析逻辑一律不动。
4. 文档：`.env.example` 在 AI 通道段补 `LLM_TIMEOUT_SECONDS=30` 说明；
   `docs/gray-runbook.md` 配置段补一句慢中转调大建议。不升版本（总验收统一升）。

## 三、边界（盘点结论：纳入 / 不纳入）
全仓 `timeout=` 盘点（2026-11-04）：
- **纳入可配置（默认值来源）**：`_chat_json`、`_chat_text`、`_router_data`、
  `router.invoke` 的默认参数——皆为主通道默认口径。未显式传 timeout、随默认
  一并变 30 的调用路径（评审全量核验）：经 invoke/_router_data 的 gateway
  judge_tribulation/generate_world_event/judge_combat 与 NPC 三处
  （npc_agenda/npc_mind/npc_proactive）；经 _chat_json 直调的 gateway
  心魔场次/心魔裁定/自由言行与 adventure/chat_actions/forge/memory 及
  server/world 两处（AI 悟方、NPC 对话）；经 _chat_text 的仅心魔文本一处
  （books 的 8.0 为显式传参，不受影响）。均属主通道，符合本意。
- **保持独立（显式值不动）**：
  - 健康探针 `probe_ai_channel` 显式传 12.0——探针须短超时，不随主通道放大；
  - CCSwitch 路径 `_anthropic_chat_json` 默认 30.0 与 `_chat_json` 内
    `max(timeout, 30.0)` 下限——既有口径不动；
  - 业务调用点显式短超时：自创功法 25.0、omen 20.0/8.0、ai_flavor 12.0/10.0、
    books 8.0、collusion 15.0、name_registry 12.0——调用方有意设定，不动；
  - `server/client.py` urllib 120s——客户端轮询，非 LLM 通道，不动。
- 配置冻结：`config` 常量在导入时冻结，改 .env 后须重启进程生效（与
  LLM_API_KEY 等既有口径相同，runbook 已有重启口径，不新增热加载）。

## 四、验收标准
- `tests/test_llm_timeout.py` 覆盖：默认 30（子进程无 env 导入断言）；env 覆盖
  生效（子进程设 45 → 45）；钳制（2 → 5、999 → 120）；非法回退（abc/空/nan/inf
  → 30）；`_chat_json`/`_chat_text` 默认调用时 httpx 收到的 timeout 恰为
  config 值（mock httpx 断言）；显式传参透传不变（12.0）；探针仍传 12.0。
- 全量回归 0 失败（基线 533 + 新增）。
- .env.example 与 runbook 文档更新到位。

## 五、Out of Scope
- 按场景（scene）分别配置超时；超时热加载；重试次数/退避可配置；
- 探针与各业务显式短超时的统一收编；版本号与 CHANGELOG（总验收统一处理）。
