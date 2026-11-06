---
feature: ui-cli-parity
status: delivered
updated: 2026-09-09
branch: (no-git-in-place)
commits: n/a
---

# UI / 局域网服与 CLI 指令对齐

## Report

**What was built** — 局域网服补齐 CLI 缺口：`/探查` `/挂赏` `/接令` `/支取` `/寄售` `/买寄售` `/撤单` `/自创功法` `/大事记`，以及 `/世情` `/打坐` `/俸禄` 别名。`/坊市` 列出寄售编号。网页侧坊市区增加对应按钮与弹层。

**Verification** — `test_cli_parity.py` PASS。

**Journey log**
- 缺口在 server 不在 CLI 本体。
- 测试需在 import 后清空 config/gateway 的 KEY，否则 .env 会覆盖。

## [S1] Problem
网页提示「未知指令」；`/自创功法` 等仅 CLI 有。

## [S2] Design
与 CLI 同语义；寄售/告示编号 1-based。

## [S3] Out of Scope
CLI 交互式转世向导。

## Tasks
- [x] T1–T5 全部完成
