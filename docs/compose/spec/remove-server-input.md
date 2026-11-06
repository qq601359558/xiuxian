# 去掉登录页宗门阵枢输入框，同源直连

- 基线：worktree `feat/remove-server-input`，HEAD `2626704`
- 状态：**已 supersede** —— 本 spec 的移除方案不再实施，见末尾「需求变更记录」。
  原 D1 裁定随之失效（`workbench.js` 登录路径仍由 `218b5aa` 改动，但改的是
  默认基址而非删除引用）。本文档保留为历史记录，不删除。
- 相关：`web-static-hosting`（v0.3.2 同源托管已落地）、`2626704`
  （远端打开时忽略存下的本机回环地址，本改动的直接前置补丁）

## 阶段一 · 五步推演（简写）

### 1. 本质解构

- **表层需求**：Martinez 原话：「宗门阵枢为什么用127.0.0.1:8765不行，是不是可以吧这个去掉」。
- **本质诉求**：玩家打开游戏页面就能玩，不用理解、不用填服务器地址；
  填错地址（最常见的就是默认的 `127.0.0.1:8765`）只会连不上。
- **为什么 127.0.0.1 不行**：`127.0.0.1` 是本机回环地址，在谁的设备上就
  指向谁自己的设备。游戏服在 NAS 上，玩家手机/电脑上的 `127.0.0.1:8765`
  永远没有游戏服，所以永远连不上。这不是 NAS 或网络故障，是地址语义本身错了。
- **为什么现在可以去掉**：v0.3.2 起游戏服自己托管网页（5 路径白名单，
  `GET /` 即登录页），玩家唯一正式用法就是打开游戏服同源页面。
  页面从哪打开，服就在哪，API 基址恒为 `window.location.origin`，
  手填入口已无存在的理由。页脚文案早已写明「打开哪个地址，就连那个服，
  不用填地址」——去掉输入框只是让界面与这句话一致。
- **验收标准**：登录页没有任何可填的服务器地址；从同源打开页面可直接
  注册/登录；旧浏览器里存过的自定义地址不再生效。

### 2. 可行性评估

- 技术可行性：**高**。同源基址逻辑在 `web/app.js` 已存在（`location.origin`
  分支），本改动是删除手填分支、把同源分支变为唯一分支，无新技术、无协议改动。
- 性能/成本：零新增开销；删除代码与一处 DOM，登录请求次数不变。
- 唯一风险点：见 D1——实际承担登录的不是 `app.js` 而是 `workbench.js`
  （见 Design §5），范围裁定是本轮唯一的卡点。

### 3. 不足与盲区

- **旧存量地址**：老玩家浏览器 `localStorage` 里可能存有 `td_base`
  （`app.js`）/`wb.base`（`workbench.js`），其中很可能就是 `127.0.0.1:8765`。
  只删输入框不处理存量，等于留着一个看不见的手填地址。新版必须彻底
  不再读取这类旧键（只删除键不够，须做到“读不到”）。
- **删除元素的连带引用**：`#serverUrl` 被三处 JS 引用（`app.js` 两处、
  `workbench.js` 三处，见 Design），删元素不改引用会抛 `TypeError`。
- **`file://` 直接打开**：`location.origin` 在 `file://` 下为 `"null"`，
  同源直连不覆盖“双击本地文件打开页面”的用法。该用法自 v0.3.2 起已不是
  正式用法（正式用法是打开游戏服地址），本轮明确不再支持，不另做回落。
- **离线演示不受影响**：`玄黄镜演（离线演示）`按钮不走服务器基址，本轮不动。
- **多服/切服**：有玩家想连别人的服时将无入口，这是去掉输入框的既定代价，
  属于 Out of Scope，不做任何替代入口。

### 4. 举一反三

- **横向**：同类“可填可不填、填错就坏”的入口只剩这一处；`workbench.js`
  第 138 行 `wb.base` 默认 `http://127.0.0.1:8765` 是同类残留，本轮只记录
  （见 Design §4），不顺手扩大。
- **纵向**：将来若真要多服/切服，应以“服列表由服端下发/扫码入服”等产品形态
  重新设计，而不是把手填框加回来。
- **涟漪面**：登录/注册请求、会话恢复（`td_token`/`wb.token` 续玩）、
  `/health` 探测、契约测试 `test_web_hosting.py`（断言了输入框存在）、
  `test_qa2_frontend_contract.py`（解析 `app.js` 的 `st.*` 键，不涉地址逻辑）。

### 5. 完善方案

推荐路径：删输入框 + 删按钮 + 基址恒为同源 + 旧存量地址一律忽略 +
契约测试同步更新并新增覆盖（Design §1–§3）。备选“保留输入框但隐藏/禁用”
被否决：留着不可见的手填逻辑等于留着故障源，且测试无法断言“无此入口”。
唯一未决项是 D1（`workbench.js` 登录路径是否同轮改），见 Design §5。

## Problem

### 现状（核查于基线 `2626704`，以 worktree 现状为准）

| 位置 | 现状 |
|---|---|
| `web/index.html:100-101` | 登录表单含 `宗门阵枢` 输入框 `#serverUrl`（占位文案“留空使用当前页面地址”） |
| `web/index.html:106` | `感应阵枢灵脉` 按钮 `#btnProbe` |
| `web/index.html:115-117` | 页脚文案已称“打开哪个地址，就连那个服，不用填地址”——与输入框的存在自相矛盾 |
| `web/app.js:6-18` | `state.base`：远端页面时丢弃存下的回环地址（`2626704` 补丁）、否则读 `localStorage.td_base`，最后回落 `http://127.0.0.1:8765` |
| `web/app.js:1889-1894` | 登录时读 `#serverUrl`，写回 `state.base` 并 `localStorage.setItem("td_base", …)` |
| `web/app.js:2408` | 启动时回填 `#serverUrl` 为 `state.base` |
| `web/workbench.js:138` | `wb.base` 默认 `http://127.0.0.1:8765`（本轮不改，见 §4） |
| `tests/test_web_hosting.py:89` | `test_root_serves_login_page` 断言登录页含 `id="serverUrl"`——改动后此断言必失败，须同步更新 |

### 关键核查结论（实现前必须知道）

1. **登录页实际加载的 JS 只有 `web/workbench.js`**（`index.html:313`），
   `web/app.js` 不被任何页面引用（`server/app.py` 白名单仍托管 `/app.js`，
   但无页面加载它；`app.js` 的 `authJoin` 读的是 `#btnJoin/#username/#playerName`，
   这些 id 只存在于不对外托管的 `web/prototype.html`）。
   因此：只改 `app.js` 修不好玩家实际走的登录路，只改 `index.html` 则会
   弄坏它——见 D1。
2. `tests/test_qa2_frontend_contract.py` 不断言地址逻辑（只解析 `app.js`
   的 `st.*` 键与 `index.html` 的 `data-cmd`），本轮无需改它；
   但 `app.js` 清理时不得破坏它解析的 `st.*` 读取形状（本轮只删基址逻辑，
   不碰状态读取，故无影响）。
3. `tests/test_web_hosting.py:97-102` 已断言登录页不得出现 `127.0.0.1`，
   去掉输入框后该断言继续成立（`index.html` 内将不再有任何 `127.0.0.1`）。

## Design

### §1 `web/index.html`：去掉输入框、按钮及相关提示

- 删除 `宗门阵枢` 字段整块（`label[for=serverUrl]` + `input#serverUrl`，
  约 100–101 行）。
- 删除 `感应阵枢灵脉` 按钮 `#btnProbe`（约 106 行）。
- 保留页脚「打开哪个地址，就连那个服，不用填地址。」（改动后此话终于为真，
  无需改文案）；保留 `玄黄镜演（离线演示）` 按钮与登录/注册其余字段原样不动。
- 删除后全仓不得再有对 `#serverUrl` / `#btnProbe` 的引用
  （`workbench.js` 的三处见 §5 裁定；`prototype.html:486` 的同名输入框
  是不对外托管的开发原型，本轮不动）。

### §2 `web/app.js`：基址恒为同源，清理手填读写与回环补丁

- `state.base` 的整段 IIFE（约 6–18 行）替换为恒为同源：
  `base: window.location.origin`（http(s) 页面下即为游戏服地址）。
  一并删除：
  - `localStorage` 的 `td_base` 读/写（初始化读、`authJoin` 的写）；
  - `2626704` 的「丢弃已存回环地址」补丁逻辑（正则判回环、`removeItem`、
    `127.0.0.1:8765` 回落分支）——补丁的前提（允许存自定义地址）已不存在，
    留着是死代码；
  - 约 1889 行 `authJoin` 里读 `#serverUrl` 并写回 `state.base` 的两行；
  - 约 2408 行启动回填 `$("serverUrl").value = state.base;`。
- **存量兼容口径**：旧浏览器 `localStorage.td_base` 里无论存着什么
  （含 `127.0.0.1:8765`、含其他服地址），新版一律不读、不删亦可
  （不读即等价于忽略；如实现顺手 `removeItem` 清理亦可，但不得因此再引入
  读分支）。`td_token` / `td_uid` / `td_user` / `td_name` 等会话键不受影响，
  会话恢复流程不变。
- `api()` 及之后全部请求（登录/注册/`/action`/`/world/director`/
  `/commands` 等）均走 `state.base`，行为上即同源；除基址来源外不改任何
  请求形状、字段与错误处理。
- `file://` 直接打开页面时 `location.origin` 为 `"null"`，本轮不做回落、
  不提示、不兼容（正式用法是打开游戏服地址，见 §3 边界）。

### §3 登录/注册/进入游戏：逻辑与其它面板不动

- 登录/注册表单字段、校验（用户名必填、密码 ≥ 6 位）、`dead:true` 死亡结算
  分支、转世入口、会话恢复、登出、离线演示、主界面各面板与指令栏均不动。
- 只改“基址从哪来”，不改“请求发什么、收到后做什么”。

### §4 `web/workbench.js`：本轮不改默认值，只记录现状

- 第 138 行 `base: localStorage.getItem("wb.base") || "http://127.0.0.1:8765"`
  本轮不改。记录在案：它是另一套独立的基址来源（`wb.*` 键），与 `app.js`
  的 `td_base` 互不相通；它是玩家实际打开的登录页所用的基址默认值。
- 但第 138 行之外的三处 `#serverUrl` 引用是否改动，见 §5 裁定 D1——
  这是本 spec 唯一未决点。

### §5 待裁定 D1：`workbench.js` 的 `#serverUrl` 引用（范围冲突）

**事实**：`workbench.js` 是登录页实际执行的登录路径，三处引用 `#serverUrl`：

| 位置 | 代码 | 删输入框后若不改的后果 |
|---|---|---|
| 约 6520 行 `doAuth` | `($("serverUrl").value \|\| state.base \|\| "").trim()` | `$("serverUrl")` 为 `null`，`.value` 抛 `TypeError`，**点登录直接崩，登录功能全坏** |
| 约 6581 行 `probeServer` | 同上读法 | 按钮已随输入框删除而不复存在，函数成死代码；但留着无害（无调用方） |
| 约 6666 行 `tryRestore` | `if ($("serverUrl")) $("serverUrl").value = state.base;` | 已有 null 守卫，安全，无需改 |
| 约 6704 行绑定 | `$("btnProbe") && …addEventListener("click", probeServer)` | 已有 null 守卫，按钮删除后安全，无需改 |

**结论**：按任务原定范围（只改 `index.html` + `app.js`，`workbench.js`
只记录第 138 行）实施，验收 A5（隔离服冒烟：注册登录成功）**必然失败**。
本 spec 不擅自扩大范围，提请裁定，二选一：

- **推荐 A（改动最小且闭环）**：将 `workbench.js` 的登录路径同轮改掉——
  `doAuth` 改为基址恒为 `location.origin`（http(s) 下；与 §2 同口径），
  不再读 `wb.base`、不再读 `#serverUrl`；`probeServer` 随按钮一并删除；
  `tryRestore` 的回填行删除。第 138 行的 `wb.base` 默认值字面本身可保留
  （其余 `wb.*` 读法——`api()` 等——仍以 `state.base` 为准，不再受它支配；
  或实现时将其初始化一并改为同源，效果等价，由实现者按最小 diff 定）。
  旧 `wb.base` 存量与 `td_base` 同口径：一律不再读取。
- **备选 B（不改 `workbench.js`）**：不可行——除非保留一个隐藏的
  `#serverUrl` 输入框供 `doAuth` 读取，这与“去掉输入框”的需求本身矛盾。
  故 B 仅记录为已否决项。

**D1 裁定前不得进入实现。** 裁定为 A 时，§1 的“全仓无引用”与验收 A1–A5
按 A 方案执行；§4 的“第 138 行不改”收窄为“第 138 行字面默认值不主动改，
但其值不再决定登录基址”。

### §6 契约测试同步更新并新增覆盖

- `tests/test_web_hosting.py`：
  - `test_root_serves_login_page`：把“断言含 `id="serverUrl"`”改为
    “断言不含 `id="serverUrl"` 且不含 `id="btnProbe"`”（登录页标志改为标题即可）。
  - 新增 `test_login_page_has_no_server_input`（或并入上条）：
    登录页源码不含 `serverUrl`、`btnProbe`、`宗门阵枢`、`感应阵枢灵脉`。
  - 新增 `test_app_js_same_origin_base`：`web/app.js` 不含 `td_base`、
    不含 `127.0.0.1`、不含 `localStorage.getItem("td_base")`；
    基址为 `window.location.origin`（字面断言）。
  - 若 D1 裁定为 A，新增 `test_workbench_same_origin_base`：`web/workbench.js`
    不含对 `#serverUrl` 的无守卫读取（`$("serverUrl").value` 出现次数为 0，
    或仅存留带 null 守卫的 `tryRestore` 行——以实现定稿为准，测试断言须与
    实现一致，不得含糊）。
  - `test_login_page_has_no_loopback_default` 保持不变（仍须通过）。
- `tests/test_qa2_frontend_contract.py`：无需改动（无地址逻辑断言）；
  回归时照常全过。
- 不新增服务器端测试：托管白名单、API 形状均不动。

## Out of Scope

- 不改 `web/workbench.js` 第 138 行 `wb.base` 默认值本身（D1 裁定为 A 时，
  仅改登录路径的基址来源，见 §5）。
- 不改服务器托管白名单（`server/app.py` 的 5 路径）、端口、启动方式、API 形状。
- 不改登录流程本身（字段、校验、死亡结算、转世、会话恢复、离线演示）。
- 不做多服/切换服/服列表功能，不留任何手填地址的替代入口。
- 不删 `web/app.js` 文件本身（仍被白名单托管、仍被 QA2 测试解析；
  仅清理其中基址逻辑）；不动 `web/prototype.html`（不对外托管的开发原型）。
- 不改样式：删除元素后如有孤立的 `.field` / 按钮样式残留，由实现者确认
  无全局影响即可，不另立样式清理任务。

## Acceptance

- A1：登录页 DOM 无 `#serverUrl` 与 `#btnProbe`：`GET /` 返回的
  `index.html` 源码不含 `id="serverUrl"`、`id="btnProbe"`、
  `宗门阵枢`、`感应阵枢灵脉`；页脚「打开哪个地址，就连那个服，不用填地址。」
  保留。
- A2：`web/app.js` 无自定义地址读写与回环回落：源码不含 `td_base`、
  `127.0.0.1`、`$("serverUrl")`；基址恒为 `window.location.origin`；
  旧 `localStorage.td_base` 存量在新版下不被读取。
- A3：登录/注册请求走同源：登录与注册仍发往同源 `/login` / `/register`
  （除基址来源外请求体、字段、校验、死亡分支均与改动前一致）；
  会话恢复（`td_token` 续玩）行为不变；离线演示按钮可用。
- A4：契约测试全过：`tests/test_web_hosting.py`（更新后）与
  `tests/test_qa2_frontend_contract.py` 全过；其余相关套件无新增失败。
- A5：隔离服冒烟（D1 裁定为 A 后执行）：在隔离环境起服，同源打开登录页，
  注册新账号成功、登录成功、进入主界面且一次 `/look` 往返成功；
  浏览器控制台无 `TypeError` / `#serverUrl` 相关报错。
- A6：回归面确认：`git diff` 只触及 `web/index.html`、`web/app.js`、
  `tests/test_web_hosting.py`（D1 裁定为 A 时另加 `web/workbench.js`
  的登录路径三处）——无其他文件改动。

## 需求变更记录（2026-11-06，supersede 本 spec 的移除方案）

### Martinez 微信纠正原话（新口径，取代移除方案）

> 登录页服务器地址默认值定为 `http://mn.20230803.xyz:8765`（他的 NAS 公网域名）；
> 页面打开时若没有存过地址、或存的是回环地址（`127.0.0.1`/`localhost`），
> 连接基址一律用该域名；输入框保留并预填该默认地址；不许再出现 `127.0.0.1`
> 作为玩家默认/占位/回落。核心验收：玩家打开登录页，默认就连
> `mn.20230803.xyz:8765`，不用填任何东西就能登录。

本 spec 上文的移除方案（删除 `#serverUrl` 输入框、基址恒为同源）**不再实施**，
A1–A6 中的移除验收随之作废；D1（`workbench.js` 登录路径是否同轮改）也不再是
待裁定项——`workbench.js` 的登录路径确实被改了，但改法是换默认基址而非删除引用。

### `218b5aa` 已实现的内容（远端 main，并行线推送）

- 三处默认一致，均为 `http://mn.20230803.xyz:8765`：
  `web/index.html:101` 占位 `placeholder="http://mn.20230803.xyz:8765"`、
  `web/workbench.js` 默认基址（IIFE）、`web/app.js` 默认基址（IIFE）。
- 无存量地址时默认 NAS 域名；存下的回环地址（`localhost`/`127.0.0.1`，含端口）
  一律丢弃（`removeItem` 后按无存量处理）；存下的非回环自定义地址仍优先。
- 输入框 `#serverUrl` 保留、可改；`tryRestore` 回填 `state.base`，打开即预填
  NAS 域名；`doAuth` / `probeServer` 读输入框值（已预填）或 `state.base`，
  登录/注册请求走该基址。
- 页脚改为「默认阵枢：`mn.20230803.xyz:8765`，换服可改。」
- 新增托管测试 `test_login_page_default_server_is_nas_domain`：断言三处默认一致，
  且 `|| "http://127.0.0.1:8765"` 不得出现。
- 补齐小修（本 worktree）：`web/README.md` 玩家指引的两处 `127.0.0.1:8765`
  改为 NAS 域名（打开地址与备用填写地址）。

### 例外（据实注明，评审裁定）：本机回落分支仍保留

`218b5aa` 在 `web/workbench.js:147` 与 `web/app.js:18` 保留了本机调试分支：

```js
var local = location.hostname === "localhost" || location.hostname === "127.0.0.1" || location.protocol === "file:";
return stored || (local ? "http://127.0.0.1:8765" : "http://mn.20230803.xyz:8765");
```

- 该分支**只在页面本身从 `localhost` / `127.0.0.1` / `file:` 打开时触发**；
  玩家经 NAS 域名（`mn.20230803.xyz:8765`）打开页面时永远走 NAS 域名。
- 测试断言禁止的是无条件默认 `|| "http://127.0.0.1:8765"`，该三元回落分支
  不在此列，测试照常通过。
- 保留理由：删掉它会让本机隔离冒烟无法自连（隔离服经 `127.0.0.1` 打开登录页
  时需回落到本机隔离服）。本轮**不擅自删除**；它与新口径「不许再出现
  `127.0.0.1` 作为玩家默认/占位/回落」是否存在冲突，由评审裁定。
- 另两处与玩家默认无关的 `127.0.0.1` 残留（仅记录，不改）：根目录
  `workbench.js:93` / `index.html:101,112`（另一条工作流保留的根文件，
  不由游戏服托管、不对外）；`docs/nas-deploy.md:115` 的 NAS 本机健康检查
  命令（在 NAS 上执行，`127.0.0.1` 即 NAS 自身）；历史 spec/report 文档中
  对旧行为的记述。

### 新验收（取代 A1–A6 的移除验收）

- N1：登录页占位与页脚均为 NAS 域名，`index.html` 不含 `127.0.0.1`。
- N2：`workbench.js` 与 `app.js` 默认基址均为 NAS 域名；无存量/存回环时
  基址为 NAS 域名（经 NAS 域名打开时）。
- N3：输入框打开时预填 NAS 域名（`tryRestore` 回填链路）。
- N4：登录/注册请求走 NAS 域名基址；不填任何东西即可登录。
- N5：契约测试 `test_web_hosting.py`（含新增断言）与
  `test_qa2_frontend_contract.py` 全过；全量回归无新增失败。
