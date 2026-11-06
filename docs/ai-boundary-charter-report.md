# PROX-7《AI 边界宪章》核查与交付报告

| 项目 | 记录 |
|---|---|
| 日期 | 2026-10-28（Asia/Shanghai） |
| 交付状态 | 阶段一设计草案已产出，待全员评审定稿；不等于实现完成或 QA 验收通过 |
| 正文 | `docs/ai-boundary-charter.md`；附件为完整设计产物，不依赖读者访问本机路径 |
| 源码基线 SHA | `e6a4d5a071df69c387dfd8c2052605f6819d47f7` |
| 分支 | `feat/character-integrity-and-audit-rules`；文档尚未提交或推送，无新的交付 commit SHA |
| 执行边界 | 使用项目指定的本地 in_place 工作区；仅写设计文档，不切分支，不改业务/测试/存档 |
| 既有工作保护 | 保留原有 `AGENTS.md`、`web/index.html`、`web/workbench.css`、`web/workbench.js` 和运行时目录改动 |

## 1. 交付内容与工程范围

- 宪章覆盖 L0–L4、事前/事中/事后闸门、R1–R10 规范性断言、逐条测试承载清单、32 场景权限归属与差距表、备用/未注册路径、不约束范围和定稿后的实施衔接。
- 以明确列举和源码纠正“8 键”为 9 键，未扩/删现行白名单。
- 第 6 节的十条验收用例是未来实现任务输入，**没有新增或修改任何测试文件**；没有编写业务实现。
- 本任务处于需求/架构设计阶段，不启动 compose-next 实现、不生成已定稿实施 Spec、不声称通过独立 review；负责人组织 PVDA 影响确认、全员评审后再正式派发。

## 2. 核查结论（不是合规率）

| 核查项 | 当前版本证据结论 |
|---|---|
| 注册场景 | 32 个，正文差距表逐行完整且顺序匹配 `PROMPT_BUILDERS` |
| 路由路径 | 8 个 scene 有显式统一入口调用；npc_talk 另有 web 旁路，world_arc_stage 构建参数不匹配；不能称八个完整成功链路 |
| 事实注入 | 6 个 scene 主路径确有 FactPack 序列化；心魔开场文字 AI 回退无包；npc_talk/npc_agenda 是传入而未注入，不算可信事实覆盖 |
| 必包规格 | 11 个 requires_facts，不是全 32 个 |
| 提案门禁 | 5 个 scene 主路径有 G，世界导演另有 D；局部 DSL、数值钳制和对象 validator 不代表完整边界 |
| 关键风险 | AI 胜负字段仍决定结局；纯 narrative 可携数值效果；缺可信事实/正文核查/奖励来源；审计失败可静默；文案名称可再晋升为地点 |
| 回归含义 | 下述测试仅验证既有事实/入口/守恒模块的局部基线；没有宣称十条红线已实现 |

## 3. 测试基线与回归证据

环境：Windows PowerShell，仓库虚拟环境 Python 3.11.0、pytest 9.1.1。测试范围为 `tests/test_ai_platform.py`、`tests/test_gate_facts.py`、`tests/test_character_integrity.py`，共 20 个 pytest 用例。

正式记录的基线与复跑通过一次性命令调用 `pytest.main`；禁用缓存/字节码，临时重定向 SQLite、提案审计与调用日志，禁止实际 socket 连接。未调用真实模型，也未用在线服务结果代替本地测试。

| 时点 | 真实输出 | 口径 |
|---|---|---|
| 文档修改前基线 | `20 passed in 0.84s`；`OFFLINE_GUARD=active; LOG_AND_DB_PATHS=temporary; EXIT_CODE=0` | 上述三个文件，20 用例；该范围无 `PRE-EXISTING` 失败 |
| 文档交付前回归 | `20 passed in 0.54s`；`OFFLINE_GUARD=active; LOG_AND_DB_PATHS=temporary; EXIT_CODE=0` | 同命令、同隔离范围；不将拟新增红线用例计入数量 |

可复现命令（在仓库根目录运行；只创建并自动清理自己的临时验证目录）：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
@'
import socket
import tempfile
from pathlib import Path
import config
import pytest
root = Path('.').resolve()
with tempfile.TemporaryDirectory(prefix='prox7-verify-', dir=root / 'scratch') as directory:
    isolated = Path(directory).resolve()
    isolated.relative_to(root / 'scratch')
    config.DATA_DIR = isolated
    config.DB_PATH = isolated / 'test.db'
    config.AUDIT_LOG_PATH = isolated / 'audit.jsonl'
    import ai.calllog
    ai.calllog.AI_LOG_PATH = isolated / 'calls.jsonl'
    def reject_network(*arguments, **keywords):
        raise AssertionError('PROX-7 verification forbids live network access')
    socket.socket.connect = reject_network
    result = pytest.main(['-q', '-p', 'no:cacheprovider', 'tests/test_ai_platform.py', 'tests/test_gate_facts.py', 'tests/test_character_integrity.py'])
    print('OFFLINE_GUARD=active; LOG_AND_DB_PATHS=temporary; EXIT_CODE=' + str(result))
raise SystemExit(result)
'@ | & '.\.venv\Scripts\python.exe' -
```

## 4. 一次性只读现状探针

通过注入网关、临时日志/数据库目录及断网保护，核验了下面五个源码缺口；没有写成仓库测试文件。输出记录的是**当前不满足目标的行为被复现**，不是红线测试通过，也不是业务验收。

```text
GAP_PROBE npc_talk_facts_discarded=True
GAP_PROBE npc_agenda_facts_discarded=True
GAP_PROBE world_arc_stage_extra_parameter_rejected=True; gateway_calls=0
GAP_PROBE narrative_kind_retains_numeric_effect=True
GAP_PROBE uppercase_injection_pattern_retained=True
GAP_PROBES=5 reproduced; no production data/network; these are current gaps, not redline passes
```

前两项确认“调用方传了事实包”不能冒充“模型收到事实包”；第三项确认 world_arc_stage 是尝试入口但 Prompt 构建失败；第四项确认纯叙事类型并未剥离效果；第五项确认大小写消毒有漏点。正文在相应场景行、R1/R5/R8/R9 中分别记录。

## 5. 文档自动审校与人工范围审校

交付前校验正文场景行与注册 AST 相等、无重复/遗漏；R1–R10 各有一行计划用例；五层齐全；每个场景有注册及生产路径的文件:行号；所有引用路径存在、行号有效且非空；测试承载文件存在；UTF-8 正常，常见密钥/令牌/带凭据 URL 形态未命中。

```text
DOC_CHECK scenes=32/32; redlines=10/10; layers=5/5; planned_assertion_rows=10
DOC_CHECK source_references=229 valid; existing_test_carriers=18 valid; sensitive_patterns=none; encoding=UTF-8
BLANK_LINE_REFERENCES=none
```

人工审校明确保留以下区分：登记不等于实际调用；入口不等于业务门禁；传参不等于事实注入；审计调用不等于已持久化；提案效果不等于实际 delta；已知字符串不等于合法实体；L4 自由不等于 L0/L1/L2 越权。正文与报告不包含密钥、令牌或环境变量值。

验证不包括全仓库全套测试、真实 AI 通道、服务/API 联调、压测或安全语义分类的完整样本执行。Git 提示现有文件换行及用户 ignore 配置访问警告，不是上述测试失败；未借机修改相关文件。

## 6. 待负责人组织的评审与后续

建议定稿确认：引擎最终冻结判定与有界抖动的时序；admission 故障时零新增结算及 commit 可恢复关联；听闻/追索世界拓展授权与非权威文案隔离；内容类别样本边界与版本。

提交完整宪章和本报告作为 PROX-7 附件，请产品与团队规划负责人安排阶段二影响确认与阶段三全员评审。随后另立实现/红线测试任务，优先补失败测试，再进行 compose-next 实现及独立 review，交全栈 QA 独立回归。与 PROX-6 的既有 P0 修复不互等。

**验收结论：本次仅提供设计草案与自测/核查证据；独立全员评审、实现验收与 QA 准出尚未发生，由负责人推进，不自行关单。**
