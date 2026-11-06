# Web 静态托管（游戏服直接发页面）

## Problem

玩家进游戏要两步：先自己打开 `web/index.html` 本地文件，再在页面里填服务器地址。
NAS/Docker 部署时门槛更高——非技术玩家容易卡在「页面在哪、地址填什么」。
而事实上：

- Dockerfile 已经 `COPY web/ ./web/`，页面文件就在镜像里；
- 前端 `web/app.js` 已有同源逻辑：页面从 http(s) 非 localhost 主机打开时
  自动以 `location.origin` 为服地址；
- 唯一缺口是游戏服 `server/app.py` 的 `do_GET` 只处理 API 路由，
  从不发 `web/` 下的静态文件，根路径落 404。

## Design

游戏服在 `do_GET` 里新增一个**精确白名单**静态分支（置于全部 API 路由之后、
404 兜底之前，保证 API 优先级与现状逐字不变）：

| 请求路径 | 返回文件 | Content-Type |
|---|---|---|
| `GET /` | `web/index.html` | `text/html; charset=utf-8` |
| `GET /index.html` | `web/index.html` | `text/html; charset=utf-8` |
| `GET /app.js` | `web/app.js` | `text/javascript; charset=utf-8` |
| `GET /style.css` | `web/style.css` | `text/css; charset=utf-8` |
| `GET /ailog.html` | `web/ailog.html` | `text/html; charset=utf-8` |

口径裁定：

1. **白名单精确匹配**：用固定的「路径 → 文件名」字典查表命中才发文件；
   文件名是代码内常量，绝不把用户请求路径拼进文件系统路径，
   路径穿越（`/../`、`%2e%2e`、双斜杠等）在构造上不可能。
2. **不做任意文件映射**：`web/prototype.html`（开发原型）不在白名单，不对外；
   白名单之外的 GET 路径维持现状（API 原样、其余 404）。
3. **`/ailog` 不受影响**：`/ailog` 是既有 JSON 接口，`/ailog.html` 是独立
   白名单条目，两者路径不同、互不干扰。
4. **响应头**：静态响应一律 `Cache-Control: no-cache`（灰度期页面更新频繁，
   避免玩家浏览器拿到旧页面）；带 `Content-Length`；
   `Access-Control-Allow-Origin: *` 与既有 JSON 响应保持一致。
   JS 的 Content-Type 定死为 `text/javascript; charset=utf-8`。
5. **文件定位**：按代码自身路径定位——`server/app.py` 所在目录的上一级
   的 `web/`（与 `data/` 的既有定位方式一致，与进程工作目录无关；
   Docker 中即 `/app/web`）。文件读不到时回 404 JSON，不抛异常。
6. **前端零改动**：`web/app.js` 的同源逻辑已覆盖本场景
   （127.0.0.1 打开时回退 `http://127.0.0.1:8765`，同端口时与同源等价）；
   服务器地址输入框保留，玩家仍可手动改连别的服。

## Out of Scope

- 不改任何游戏规则、API 形状、端口、启动方式；CLI 不受影响。
- 不引入静态文件框架/目录浏览/通配映射；不托管 `prototype.html`。
- 不做 gzip、ETag/Last-Modified 等缓存优化（已定 `no-cache`）。
- 不改单入口代理 `tools/public-entry-proxy.js` 本身（文档中降为可选）。

## Acceptance

- A1：`GET /` 与 `GET /index.html` 返回 200，`Content-Type` 为
  `text/html; charset=utf-8`，内容与磁盘 `web/index.html` 一致
  （含登录页标志：标题「天道因果录」与 `id="serverUrl"` 输入框）。
- A2：`GET /app.js` / `GET /style.css` / `GET /ailog.html` 各返回 200、
  类型正确（js / css / html）、内容与磁盘文件一致。
- A3：静态响应带 `Cache-Control: no-cache`。
- A4：`GET /prototype.html` → 404；`GET /../config.py`、
  `GET /%2e%2e/config.py`、`GET //etc/passwd` 等穿越/越界尝试 → 404，
  绝不返回任何文件内容。
- A5：既有 API 不回归：`GET /health` 仍 200 JSON；`GET /ailog` 仍返回
  JSON（`application/json`、含 `items`），不是 HTML 页面。
- A6：隔离服实证：从服地址 `http://127.0.0.1:<端口>/` 能加载登录页
  （curl 三路径 + Puppeteer 桌面宽度截图为据）。
- A7：文档对齐：`docs/nas-deploy.md` 玩法一节改为「打开
  `http://<NAS地址>:8765/` 一个网址即可」为首选方式；
  `web/README.md` 访问步骤同步。
- A8：全量回归 0 失败（基线 719 + 新增用例）。
