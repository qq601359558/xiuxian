# 《天道因果录》— AI 主导的文字修仙 MUD（灰度版 v0.3.2-gray.9）

一个 AI 主导的修仙游戏，功能全程使用 AI 编写。规则引擎裁决一切数值与因果，
LLM 只负责叙事、NPC 言行与事件提案 — 数值永远由规则落账，AI 不能乱改。

## 设计三句话

- **寿元是硬通货** — 1 游戏年 = 现实 1 天，一切行动烧寿元，突破是唯一「改命」。
- **世界不需要你也在转** — NPC 有欲望、仇怨与议程，会合谋、传谣；你离线世界照样推进。
- **你死后世界记得你** — 传说、仇家、未竟之业与道统，进入下一世与下一纪元（赛季 84 个现实天）。

境界：凡人 → 练气 → 筑基 → 金丹 → 元婴 → 化神 → 炼虚，含天劫、心魔、灵气总量稀释、
三护栏（新手庇护 / 安全区 / 离线归隐）、坊市四通道、悬赏因果、秘境探险、转世道统与六大排行榜。

## 快速开始

环境：Python 3.10+（已在 3.12 上验证）。第三方依赖只有 `pydantic`、`httpx`、`rich`。

```bash
git clone https://github.com/qq601359558/xiuxian.git
cd xiuxian
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

### 方式一：命令行版（单人）

```bash
python cli/main.py
```

Windows 也可以双击 `start_game.bat`（它会自动使用项目内的 `.venv`，没有则用系统 `python`）。

常用指令（游戏内输入 `/帮助` 看全集）：`/道身` `/地图` `/闭关` `/突破` `/斗法`
`/交谈` `/坊市` `/购买` `/秘境` `/宗门` `/告示` `/目标` `/世情`

### 方式二：局域网网页版（多人同界）

```bash
python server/start.py          # 权威世界服，默认监听 0.0.0.0:8765
```

然后用浏览器打开 `web/index.html`，填服务器地址（本机 `http://127.0.0.1:8765`，
局域网其他玩家填主机 IP）和道号，点「入世」。前端只做表现，数值、AI、门禁全在 Python 服。

### 方式三：NAS / Docker 部署（24 小时在线）

仓库带 `Dockerfile` + `docker-compose.yml`：把仓库放到 NAS，填好 `.env`、建个空 `data/`
文件夹，`docker compose up -d --build` 即可常驻运行（群晖 Container Manager /
威联通 Container Station / 飞牛 fnOS 也能图形化导入 compose，fnOS 另有专门小节）。存档挂载在宿主机 `data/`，升级不丢档。
完整步骤、备份与公网访问（DDNS / Cloudflare Tunnel / Tailscale Funnel）见
[NAS 部署说明](docs/nas-deploy.md)。

## AI 配置

正式体验模式（`AI_REQUIRED=1`，默认）下，交谈 / 斗法 / 自由言行等交互必须有可用的 AI 通道。
在项目根目录建 `.env`（已被 `.gitignore` 排除，不要提交）。
仓库附 `.env.example` 样例，`cp .env.example .env` 后改 Key 即可。
**开灰度服请先读 [灰度运行手册](docs/gray-runbook.md)**：开服自检、邀请、备份、排障、回滚都在里面；
版本变更见 [CHANGELOG.md](CHANGELOG.md)。

```ini
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=你的key
LLM_MODEL=deepseek-chat
```

支持任何 OpenAI 兼容接口；也可以 `USE_CCSWITCH=1` 走本机 CC Switch。
只想跑规则与测试、不接 AI 时：`ALLOW_LOCAL_AI=1`（允许本地模板降级）。

其他常用环境变量：`GAME_ENV=test|production`、`TIME_SCALE`（测试闭关倍速，生产强制 1）、
`LAN_HOST`、`LAN_PORT`（默认 8765）、`NPC_TICK_INTERVAL`（默认 120 秒）。

存档为 SQLite：`data/tiandao.db`（本地数据，不入库）。重置世界：`python tools/reset_world.py`。

## 测试

`tests/` 下有 61 个测试文件，均为可直接运行的 Python 脚本，也可用 pytest 跑：

```bash
pip install pytest
python -m pytest tests -q
# 或单个文件：python tests/test_core.py
```

## 目录

| 目录 | 内容 |
|---|---|
| `core/` | 规则引擎：修炼/突破/斗法/炼丹/宗门/坊市/因果/NPC 心智等 50+ 模块 |
| `ai/` | AI 网关与门禁：提案、事实包、校验、配额、审计 |
| `server/` | 局域网权威服（HTTP） |
| `cli/` | 命令行客户端 |
| `web/` | 网页前端（纯静态，见 `web/README.md`） |
| `storage/` | SQLite 存储层 |
| `docs/` | 玩法蓝图、产品 backlog、功能 spec（`docs/compose/spec/`） |
| `tests/` | 自动化测试 |

更完整的设计与待开发清单见 `docs/gameplay-blueprint.md` 与 `docs/product-backlog.md`，
立项需求见 `requirements_v3.md`。

## 状态

局域网原型首版。未设置开源协议，默认版权保留。
