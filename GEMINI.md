# 全局交互与工作流规则 (Global Interaction & Workflow Rules)

与 [`AGENTS.md`](AGENTS.md) 保持一致：**需求细化 → 受控开发（compose-next）→ 回归验证**。

## 阶段一：需求细化

新需求必须先执行 [`.agents/skills/requirement-evaluator/SKILL.md`](.agents/skills/requirement-evaluator/SKILL.md) 五步推演，产出真正需求（问题/契约/边界/验收/不做范围）并确认后再写业务代码。

## 阶段二：compose-next 受控开发

跨模块、改行为、需设计的任务走 compose-next：隔离工作区、`docs/compose/spec/<feature>.md`、实现、验证、独立评审。单文件小改可降级但仍须验证。

## 阶段三：回归验证

跑相关 pytest，每条验收有证据，标注 PRE-EXISTING，禁止空口交付。详细门禁见 `AGENTS.md`。
