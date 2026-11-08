# 合同审计截图索引（contract-audit，2026-11-08）

截图文件：`~/workspace/ui-shots/contract-audit/`（桌面 1280×900 为主；终端实拍为真实 stdout 渲染）。

| 截图 | 台账行 | 证明内容 |
|---|---|---|
| `sc-ca-001-terminal.png` | CA-001（P0） | 终端实拍：`/悟丹 /悟器 /生成丹药 /生成法宝` 4/4 ok，均带 recipe（大罗诛仙剑真解、玄龟宝铠铸谱、太虚仙衣云锦录、两仪周天剑匣谱）；基线为 4 条抓取失败 HTTP 500。 |
| `sc-ca-002-stone-loss.png` | CA-002（P0，SC-01） | 桌面宝图结算：蛮力破阵后结算行「灵石损耗：−40 灵石」，宝图消耗已消耗 -1，残铁古剑 攻伐 +20；toast「破阵大捷：掘得损耗灵石40」。 |
| `sc-ca-003a-loot-ceremony.png` | CA-003（P0） | 桌面得宝仪式幕：（地品），三幕 前奏/揭晓/余韵，result_ref 行含 uid/name/kind: relic/tier: 3，略过按钮在场。 |
| `sc-ca-003b-settlement.png` | CA-003（P0，SC-02） | 桌面关幕后恢复的宝图结算：天机秘宝·古阵现世破阵大典，发掘灵石 +950，宝图消耗已消耗 -1，「宝 纯阳离火印 地品·稀世重宝」遗物行，收入百宝纳戒 / 立即佩戴入体按钮在场。 |
| `sc-ca-004-sanctum.png` | CA-004（P0）、CA-005（P2） | 桌面洞府全页：剩余寿元 79.4 载（CA-005 口径）、宗门职衔 散修、本命温养法宝 青锋剑 攻伐 +20；无「神识感召 4,850步」「太上长老」「九天碧玉太虚剑」。 |
| `sc-ca-023-terminal.png` | CA-023（P1） | 终端实拍：目录 /望气 aliases `['/echo', '/天象', '/omen']`，/奇遇 aliases `[]`；分发:1959 原样在场，:2058 已为 `("/奇遇")`；`/omen` ok，返回 season_theme 静默纪元。 |

## 拍摄方式与局限

- 桌面截图：headless Chromium（/opt/meta-chromium/chrome）+ CDP 驱动，走真实登录表单与真实 DOM 点击；截图沙盒为 worktree 代码副本（8766 端口），播种账号 shot1/shot2（藏宝图原型/目标节点/穿戴均由引擎真实生成）。
- 终端实拍：`WORLD.handle` 真实调用的 stdout 原样渲染（`~/workspace/shot-xiuxian/transcripts/`），非手写。
- 局限：截图沙盒内 Chrome 无法加载 CDN（Tailwind/字体），洞府与结算截图为无 Tailwind 样式渲染——内容（数值、行、按钮）真实，布局不代表生产样式。命盘巨环为无样式下的 SVG 尺寸失控，非本次改动引入（生产样式下正常尺寸）。
- 移动端：本轮 mobile.js/mobile.css 零代码改动，无移动端消费面变化，故无移动端截图（CA-037 为服务端透传覆盖移动端）。
