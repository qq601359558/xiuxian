# 天道因果录 · 网页客户端

唯一入口：**index.html + workbench.css + workbench.js**

服务器托管：http://<本机IP>:8765/（server.run）

启动方式：

1. 启动局域网服（权威世界 + AI），在项目根目录执行：

```powershell
# Windows
.\.venv\Scripts\python.exe server\start.py
# macOS / Linux
.venv/bin/python server/start.py
```

2. 浏览器打开 `http://127.0.0.1:8765/`——游戏服自己托管网页，打开就是登录页，
   页面会自动连打开它的这个服，填道号点「入世」即可。

> 备用方式：直接用浏览器打开本目录的 `index.html` 文件（双击即可），
> 再在页面里填服务器 `http://127.0.0.1:8765` 与道号。
> 局域网内其他玩家打开 `http://<主机IP>:8765/` 即可同界游玩；
> 用本地文件打开时，把服务器地址改成主机 IP 也可。

> 前端只做表现；数值、AI、门禁全在 Python 服。

旧版 app.js / style.css 已弃用，可删除。
