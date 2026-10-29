# 局域网账号与续玩

启动服务：`python -m server.run`。网页玩家通过注册/登录进入，账号与角色道号相互独立，道号可以重名。

新玩家先注册：

```sh
curl -X POST http://127.0.0.1:8765/register -H "Content-Type: application/json" -d '{"username":"你的账号","password":"你的密匙","name":"角色道号"}'
```

换设备以账号密匙登录：

```sh
curl -X POST http://127.0.0.1:8765/login -H "Content-Type: application/json" -d '{"username":"你的账号","password":"你的密匙"}'
```

已有 token 续玩：

```sh
curl -X POST http://127.0.0.1:8765/join -H "Content-Type: application/json" -d '{"token":"登录返回的token"}'
python -m server.client join --token <token>
```

命令行账号登录建议交互输入密匙，避免密码出现在命令行历史和进程参数：

```sh
python -m server.client join <username>
python -m server.client <token> /look
```

自动化也可 `python -m server.client join <username> <password>`。以上 curl 示例为 POSIX shell 写法；PowerShell 可使用 `Invoke-RestMethod` 提交同样的 JSON。不要在不可信终端暴露凭据或 token。

`POST /join` 也接受 username/password；任何客户端自报 user_id 都不决定身份。缺少凭据返回 401 / AUTH_REQUIRED，无效凭据返回 401 / AUTH_FAILED（账号或密匙有误），不会降级成新建角色。有效 token 优先，无效 token 不会回退到同时提供的密码。已死角色认证后仍按现有规则开启新一世。

简报只接受 `Authorization: Bearer <token>`，`GET /world/briefing?uid=...` 不再提供免认证访问。静态托管只允许 web 资源和显式旧资源名，任何穿越或私有文件请求返回 404。

旧的「只凭道号登录」已移除；历史无账号 lan_ 存档不自动认领、不删除。确需恢复时由管理员核实后独立处理。曾可能通过静态路由暴露的服务密钥建议在修复部署时轮换。
