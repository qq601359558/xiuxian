# PROX-9 独立 QA 证据（服务端测试工程师）

所有执行均在 `git archive 5b93aae` 隔离副本内完成，未读取/写入真实 `data/tiandao.db`（真实存档 mtime 16:39，早于本次 QA；SHA256 仍为 9C5A…4336，属 PM 冒烟后状态）。

| 文件 | 内容 |
| --- | --- |
| red.txt | 新安全测试跑在旧源码 5b93aae 上：43 failed / 31 passed（红测成立） |
| green.txt | 同一测试跑在交付源码上：74 passed |
| full-base.txt | 旧源码全量：2 failed / 477 passed（两条 PRE-EXISTING） |
| full-final.txt | 交付源码全量（第 1 次）：3 failed / 550 passed（额外 1 条 test_qi_pace 波动，见下） |
| full-final2.txt | 交付源码全量（第 2 次，全新副本）：2 failed / 551 passed（仅两条 PRE-EXISTING，复现交付方口径） |
| qa-independent-probes.txt | 61 项自写 HTTP 探针全 PASS（穿越/静态/join/简报/注销/零副作用） |
| dead-life-2.txt | 已死角色 token & 账号两条路径均开新一世，uid 保留 |
| probe_independent.py | 探针脚本（原始 socket 发送 request-target，避免客户端归一化） |

test_qi_pace 说明：第 1 次全量中 `test_newbie_meditation_boost` 因共享库内高阶修士数量使 `global_qi_multiplier()` 下降而 `exp_gained=123 < 150`；单独复跑 5/5 通过、旧基线全量与第 2 次全量均通过，属既有测试隔离/时序脆弱，不属本单改动引入（本单未触及 core/qi.py、core/clock.py 与修炼常数）。
