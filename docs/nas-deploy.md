# NAS / Docker 部署说明

把《天道因果录》游戏服跑在家里 NAS 上：24 小时在线、关电脑不影响、局域网直接玩，
想给外地朋友玩再看最后一节公网访问。仓库根目录已备好三个文件：

| 文件 | 作用 |
|---|---|
| `Dockerfile` | 游戏服镜像（python:3.12-slim，x86 / ARM 通用） |
| `docker-compose.yml` | 一键构建启动、存档挂载、开机自恢复 |
| `.dockerignore` | 构建时排除存档、密钥、测试等无关文件 |

> ⚠️ 诚实标注：这套 Docker 打包在开发环境里**没有实测过 docker build**（开发机无 Docker），
> 只用「干净 venv 按 requirements.txt 起服」验证了运行本身没问题。
> 第一次在 NAS 上构建如果报错，把 NAS 上构建/启动的日志复制回来即可定位。

## 一、准备文件

在 NAS 上建一个文件夹（例：群晖 `docker/tiandao`、威联通任意目录），把仓库内容放进去，
至少要包含：`Dockerfile`、`docker-compose.yml`、`.dockerignore`、`config.py`、`requirements.txt`，
以及 `ai/ cli/ core/ server/ storage/ web/ tools/` 这些目录（直接整仓拷过去最省事）。

然后在同目录下再建两样东西：

1. **`.env` 配置文件**：把 `.env.example` 复制一份改名为 `.env`，按下节填好。
2. **空的 `data/` 文件夹**：存档就落在这里（数据库 `tiandao.db`、赛季文件、日志）。
   容器只是借这个文件夹存东西，镜像升级、重建都不会动它。

## 二、填 .env

最关键三行（AI 通道，正式体验必填）：

```ini
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=你的密钥
LLM_MODEL=deepseek-chat
```

长期开服建议再改一行运行环境：

```ini
GAME_ENV=production
```

`.env.example` 默认是 `test`（联调用，闭关时间有加速）；`production` 下游戏时间与现实 1:1 同步
（1 游戏年 = 现实 1 天），才是这款游戏的正常节奏。其余项保持默认即可，端口固定 8765。

## 三、启动（二选一）

### 路线 A：图形界面导入 compose

**群晖（Container Manager）**

1. 打开 Container Manager → 「项目」→「新增」。
2. 项目名称填 `tiandao`，路径选第一步建的文件夹（它会自动认出里面的 `docker-compose.yml`）。
3. 来源选「使用现有的 docker-compose.yml」，下一步开始构建，构建完自动启动。
4. 在「容器」页看 `tiandao` 容器状态变绿 / healthy 即成功。

**威联通（Container Station）**

1. 打开 Container Station → 「应用程序」→「创建」。
2. 把 `docker-compose.yml` 的内容粘贴进去（或用导入文件），应用名称填 `tiandao`，点创建。
3. 等构建完成、容器状态为运行中即成功。

**飞牛 fnOS（图形界面 / SSH 两条路线）**

fnOS 的 Docker 应用支持 Compose 项目，两种走法任选其一。
注意：本项目的 compose 用的是 `build: .`（现场按同目录的 Dockerfile 构建镜像），
所以**不能只导入一个 compose 文件**——必须先把整个项目文件夹备好在 NAS 上。

先说镜像加速（两条路线通用）：首次构建要从 Docker Hub 拉 `python:3.12-slim` 基础镜像，
国内网络直连可能很慢甚至失败。构建卡住先别急着重试，去飞牛 Docker 的设置里
配置镜像加速（加速地址按你手头可用的填），再重新构建。

图形界面路线：

1. 把整个项目文件夹（含 `Dockerfile` 与全部源码）通过飞牛文件管理上传到 NAS，
   放一个目录里（例：`docker/tiandao`）；并在这个文件夹里按第一、二节备好两样东西：
   复制 `.env.example` 为 `.env` 填好（缺了它构建/启动会因没配置失败）、建空的 `data/` 文件夹。
2. 打开 Docker → 「项目」→「新增 / 新建项目」，导入该文件夹里的 `docker-compose.yml`
   （指向文件夹里的 compose 文件），项目名填 `tiandao`，开始构建并启动。
3. 容器状态变为运行中后，浏览器打开 `http://<NAS的局域网IP>:8765/health`，
   看到 `{"ok": true, ...}` 即成功；首次启动有开服补算，耐心等 1–3 分钟（见第四节）。
4. 玩法见第五节：打开项目里的 `web/index.html`，服务器地址填
   `http://<NAS的局域网IP>:8765`；或用单入口代理（8080）合成一个入口。

SSH 路线（适合想全程命令行的）：

1. 开 SSH：飞牛网页后台 → 设置 → SSH → 打开开关（默认端口 22），
   用管理员账号密码登录 NAS，再 `sudo -i` 提权到 root。
2. 选一个放项目的目录，拉代码：

   ```bash
   git clone https://github.com/qq601359558/xiuxian.git
   cd xiuxian
   ```

   仓库是公开的，可直接克隆；若提示没有 `git` 命令，二选一：
   在电脑上从 GitHub 下载 ZIP、解压后用飞牛文件管理上传整个文件夹，或先装 git 再克隆。
3. 备配置并建存档目录，然后构建启动：

   ```bash
   cp .env.example .env   # 按文件里的注释填 AI 密钥等，并把 GAME_ENV 改成 production
   mkdir -p data
   docker compose up -d --build
   ```
4. 等 1–3 分钟开服补算，浏览器打开 `http://<NAS的局域网IP>:8765/health`
   看到 ok 即成功；玩法同上（第五节）。常用运维命令见路线 B。
5. 安全提醒：部署完成后可以把 SSH 开关关掉，日常管理走飞牛网页后台即可。

### 路线 B：命令行（SSH 登录 NAS 后）

```bash
cd /path/to/tiandao          # 换成你放文件的目录
docker compose up -d --build # 构建并后台启动
docker compose logs -f       # 看启动日志（Ctrl+C 只退出看日志，不停服）
curl http://127.0.0.1:8765/health   # 返回 {"ok": true, ...} 即起来了
```

常用运维：

```bash
docker compose restart        # 重启
docker compose down           # 停服（存档在 data/ 里，不受影响）
docker compose up -d --build  # 升级：先换上新版代码文件，再跑这条重建
```

## 四、首次启动要耐心

游戏服启动时会做「开服补算」：把世界离线期间的 NPC 行动、寿元流逝等一次结算完。
全新世界一般几十秒；**玩过一阵子的存档可能要几分钟**，期间 `/health` 还连不上是正常现象，
compose 的健康检查已经给了 3 分钟宽限。不要因为一时打不开就反复重启容器——
等日志里出现监听提示、`/health` 返回 ok 再进游戏。

## 五、局域网里怎么玩

游戏服接口在 `http://<NAS的局域网IP>:8765`。网页不在容器里托管，按下面任一方式打开：

- **简单法**：把 `web/index.html` 在玩家电脑/手机上打开（本地文件即可），
  在页面里把服务器地址填 `http://<NAS-IP>:8765`，输入道号点「入世」。
  游戏接口已开跨域，网页放哪都能连。
- **单入口法（可选）**：仓库带了 `tools/public-entry-proxy.js`（需要 Node.js 环境），
  在 NAS 或任意一台常开机器上 `node tools/public-entry-proxy.js`，
  它会把网页和游戏接口合成一个入口（默认 8080 端口），玩家只开
  `http://<NAS-IP>:8080` 就能玩，不用填服地址。公网访问时也推荐用这个单入口。

## 六、存档与备份

- 所有存档都在部署目录的 `data/` 里：`tiandao.db`（角色/世界数据库）、
  `season_epoch.txt`（赛季起点）、若干日志文件。**备份 = 复制整个 `data/` 文件夹。**
- 复制前先 `docker compose down` 停服最稳妥（避免复制到写一半的数据库）；
  也可以用群晖 Hyper Backup / 快照给这个文件夹设定时备份。
- 升级游戏版本只换代码文件并 `--build` 重建，`data/` 不要动，存档自动延续。

## 七、公网访问（给不在同一局域网的朋友玩）

先分清你家宽带是哪种情况，再选路线。

### 1）自查有没有公网 IP

1. 登录路由器后台，记下 WAN 口（互联网侧）显示的 IP 地址。
2. 手机关 WiFi、用流量打开任意「IP 查询」网站，记下显示的 IP。
3. 两个 IP **一致** → 有公网 IP，走路线 A；
   **不一致**，或 WAN IP 落在 `10.x` / `100.64–100.127.x` / `172.16–31.x` / `192.168.x`
   这些段里 → 是运营商 CGNAT 大内网，**没有公网 IP**，端口转发做不了，走路线 B。

国内家用宽带目前多数没有公网 IP（可以打运营商客服电话申请开通，成功率看地区）。

### 2）路线 A：有公网 IP —— DDNS + 端口转发

1. DDNS：群晖 控制面板 → 外部访问 → DDNS，启用一个免费域名（如 synology.me）；
   威联通有 myQNAPcloud DDNS；其他品牌路由器多自带 DDNS。
2. 路由器后台做端口转发：用了单入口代理就转发外部 8080 → NAS 的 8080，
   玩家直接打开 `http://<你的DDNS域名>:8080` 就能玩；
   只转发 8765（游戏接口）也可以，但玩家要自己打开 `web/index.html`
   并把服务器地址填成 `http://<你的DDNS域名>:8765`。
4. 提醒：端口暴露在公网等于把游戏服挂在互联网上，自担风险；不玩时段可关掉转发规则。

### 3）路线 B：无公网 IP —— 隧道（免费，不需要公网 IP）

**Cloudflare Tunnel（cloudflared）**

- 免费，但需要一个域名并把 DNS 托管到 Cloudflare。
- 最简步骤：NAS 上（或一台常开机器上）装 `cloudflared` →
  `cloudflared tunnel --url http://127.0.0.1:8080` 可先拿一个临时公网网址试玩
  （指向单入口代理 8080；临时网址每次重启会变，长期用请在 Cloudflare 后台建正式隧道绑域名）。
- 注意：国内网络环境下 cloudflared 与 Cloudflare 边缘的连接偶有不稳定，断线重连即可。

**Tailscale Funnel**

- 免费版 Tailscale 账号即可用 Funnel；群晖/威联通都有官方 Tailscale 套件。
- 最简步骤：NAS 装 Tailscale 并登录 → 管理后台打开 Funnel →
  把 NAS 的 8080（单入口代理）暴露为 `https://<设备名>.<你的tailnet>.ts.net` 公网地址。
- 注意：Funnel 只能暴露有限的几个固定端口（443/8443/10000），地址是 ts.net 子域名；
  国内可用性同样取决于本地网络到 Tailscale/中继的连通情况，先小范围试再发朋友。

两种隧道都建议指向单入口代理（8080），这样玩家打开一个网址就能玩，
不用再单独解决网页放哪的问题。
