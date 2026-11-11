"""action-error-ux：/action 缺参 code 契约 + 双端报错原文不上界面。

- 服务端：缺 token → 400 + code AUTH_REQUIRED；有 token 缺 command → 400 +
  code EMPTY_COMMAND；error 文案与状态码不变（只增字段）。
- 前端（静态断言，沿用本仓 test_karma_chains_ui / test_chat_structure 模式）：
  双端 sendCmd 无 token 不发请求、已知错误映射成人话、后端原文不上界面、
  空指令触发点禁用发送按钮。
"""
from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- 服务端夹具
# 与 tests/test_auth_hardening.py 的 in-process 夹具同构：全新 tmp DB，
# 不连 NAS、不动线上数据。
@pytest.fixture
def api(tmp_path, monkeypatch):
    import config
    import storage.db as database
    import server.log as server_log
    from core.jianghu_sim import JianghuSimulator
    from core.npc_proactive import NpcProactiveEngine
    from core.world_director import WorldDirector

    monkeypatch.setattr(config, "BASE_DIR", tmp_path)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "world.db")
    monkeypatch.setattr(database, "DB_PATH", tmp_path / "world.db")
    monkeypatch.setattr(server_log, "LOG_PATH", tmp_path / "server.log")
    monkeypatch.setattr(JianghuSimulator, "simulate_offline", lambda **kwargs: {})
    monkeypatch.setattr(WorldDirector, "run_cycle", lambda **kwargs: {})
    monkeypatch.setattr(NpcProactiveEngine, "maybe_engage", lambda *args, **kwargs: [])
    with monkeypatch.context() as import_patches:
        import_patches.setattr(threading.Thread, "start", lambda self: None)
        import server.app as app
        import server.world as world_module

    monkeypatch.setattr(world_module.World, "_seed_npcs", lambda self: None)
    monkeypatch.setattr(
        world_module.World, "_append_natural_omen",
        lambda self, character, payload, **kwargs: payload,
    )
    world = world_module.World(auto_tick=False)
    monkeypatch.setattr(app, "WORLD", world)
    (tmp_path / "web" / "images").mkdir(parents=True)
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / ".env").write_text("LLM_API_KEY=<redacted>\n", encoding="utf-8")
    (tmp_path / "data" / "tiandao.db").write_bytes(b"SQLite format 3\x00private-save")
    for filename in ("index.html", "workbench.css", "workbench.js"):
        (tmp_path / "web" / filename).write_text("public " + filename, encoding="utf-8")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.GameHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def request(method, path, payload=None):
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=15)
        try:
            connection.request(
                method, path,
                body=json.dumps(payload).encode("utf-8") if payload is not None else None,
                headers={"Content-Type": "application/json"},
            )
            response = connection.getresponse()
            return response.status, json.loads(response.read() or b"{}")
        finally:
            connection.close()

    try:
        yield SimpleNamespace(request=request, world=world)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _post(api, path, payload):
    return api.request("POST", path, payload)


# ---------------------------------------------------------------- 服务端契约
def test_action_missing_token_has_auth_required_code(api):
    status, body = _post(api, "/action", {"token": "", "command": "/look"})
    assert status == 400, body
    assert body.get("ok") is False
    assert body.get("code") == "AUTH_REQUIRED", body
    assert body.get("error") == "需要 token 与 command", body


def test_action_missing_command_has_empty_command_code(api):
    status, body = _post(api, "/action", {"token": "some-token", "command": ""})
    assert status == 400, body
    assert body.get("ok") is False
    assert body.get("code") == "EMPTY_COMMAND", body
    assert body.get("error") == "需要 token 与 command", body


def test_action_missing_both_params_prefers_auth_required(api):
    status, body = _post(api, "/action", {})
    assert status == 400, body
    assert body.get("code") == "AUTH_REQUIRED", body
    assert body.get("error") == "需要 token 与 command", body


def test_action_missing_command_whitespace_only(api):
    status, body = _post(api, "/action", {"token": "some-token", "command": "   "})
    # 服务端 str() 不 strip：空白串按有值处理，走会话校验（200 ok:false），
    # 不得 400 冒出缺参 code；空指令由前端触发点堵住。
    assert status == 200, body
    assert body.get("code") != "EMPTY_COMMAND", body


def test_action_code_only_in_action_branch():
    src = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    start = src.index('if path == "/action":')
    end = src.index('if path == "/chat":', start)
    branch = src[start:end]
    assert "AUTH_REQUIRED" in branch, "缺 token 分支须带 code"
    assert "EMPTY_COMMAND" in branch, "缺 command 分支须带 code"


# ---------------------------------------------------------------- 登录回退快照
# NAS 实锤回归点：tick 持锁窗口登录返回 token None + ok:true 的回退快照，
# 前端不得凭 ok:true 放行进游戏；快照须带可区分 code WORLD_BUSY（只增字段）。
def test_login_lock_fallback_snapshot_has_world_busy_code(api):
    status, reg = _post(api, "/register", {"username": "持锁人", "password": "pw12345678", "name": "持锁人"})
    assert status == 200 and reg.get("ok") is True and reg.get("token"), reg
    with api.world.lock:
        status, body = _post(api, "/login", {"username": "持锁人", "password": "pw12345678", "name": "持锁人"})
    assert status == 200, body
    assert body.get("ok") is True
    assert body.get("lock_fallback") is True
    assert body.get("session_issued") is False
    assert not body.get("token"), "回退快照不得带 token"
    assert body.get("code") == "WORLD_BUSY", body
    # 释放锁后再次登录即正常发 token，且不带 WORLD_BUSY
    status2, body2 = _post(api, "/login", {"username": "持锁人", "password": "pw12345678", "name": "持锁人"})
    assert status2 == 200 and body2.get("token"), body2
    assert body2.get("lock_fallback") is False
    assert body2.get("code") != "WORLD_BUSY", body2


def test_login_dead_lock_fallback_snapshot_has_world_busy_code(api):
    # _dead_fallback_snapshot 变体（总管补充核查）：死亡角色在 tick 持锁窗口
    # 登录同样产出无 token 的 200 回退快照（既有 test_login_latency_fix 持锁
    # 死者测试已证实 token None + lock_fallback）；本测试锁定其 code。
    # 前端 doAuth 的 token 校验是 payload 通用的，活角/死者同一规则。
    from core.models import CharacterStatus
    from storage.db import CharacterRepository

    status, reg = _post(api, "/register", {"username": "持锁死者", "password": "pw12345678", "name": "持锁死者"})
    assert status == 200 and reg.get("ok") is True and reg.get("token"), reg
    char = CharacterRepository.get_by_user_id(reg["user_id"])
    assert char is not None
    char.status = CharacterStatus.DEAD
    char.death_cause = "测试坐化"
    char.death_settled = False
    CharacterRepository.save(char)
    with api.world.lock:
        status, body = _post(api, "/login", {"username": "持锁死者", "password": "pw12345678", "name": "持锁死者"})
    assert status == 200, body
    assert body.get("ok") is True
    assert body.get("dead") is True
    assert body.get("lock_fallback") is True
    assert body.get("settlement_pending") is True
    assert body.get("settled") is False
    assert body.get("session_issued") is False
    assert not body.get("token"), "死者回退快照不得带 token（否则 /转世 无会话可用）"
    assert body.get("code") == "WORLD_BUSY", body
    # 释放锁后再次登录：结算路径发 token，不带 WORLD_BUSY
    status2, body2 = _post(api, "/login", {"username": "持锁死者", "password": "pw12345678", "name": "持锁死者"})
    assert status2 == 200 and body2.get("token"), body2
    assert body2.get("dead") is True
    assert body2.get("code") != "WORLD_BUSY", body2


# ---------------------------------------------------------------- 前端静态
def _js(name):
    return (ROOT / "web" / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["mobile.js", "workbench.js"])
def test_frontend_has_humanize_helper_and_auth_mapping(name):
    js = _js(name)
    assert "humanizeActionError" in js, f"{name} 缺人话映射 helper"
    assert "requireActionToken" in js, f"{name} 缺无 token 守卫"
    assert "AUTH_REQUIRED" in js, f"{name} 映射表缺 AUTH_REQUIRED"
    assert "EMPTY_COMMAND" in js, f"{name} 映射表缺 EMPTY_COMMAND"
    assert "WORLD_BUSY" in js, f"{name} 映射表缺 WORLD_BUSY（锁忙回退）"
    assert "登录已失效，请重新登录" in js, f"{name} 缺重登人话文案"
    assert "err.code" in js or ".code" in js, f"{name} api() 须把后端 code 挂到 Error 上"


@pytest.mark.parametrize("name", ["mobile.js", "workbench.js"])
def test_frontend_doauth_rejects_tokenless_login(name):
    # NAS 实锤回归点：token 为空的登录响应不得进游戏。
    js = _js(name)
    assert "!payload.token" in js, f"{name} doAuth 须校验 token 存在"
    assert "showApp" in js
    # 忙回退：人话提示 + 自动重试一次（复用 doAuth，不新造会话机制）
    assert "服务器正忙，正在重试" in js, f"{name} 锁忙回退须提示并自动重试"
    assert "setTimeout" in js


@pytest.mark.parametrize("name", ["mobile.js", "workbench.js"])
def test_frontend_doauth_retry_timer_is_cancellable(name):
    # MF-1：自动重试定时器句柄须存入 state、可取消；手动提交/成功/非忙
    # 回退时清掉；仅无挂起定时器时调度，避免重复/过期重试。
    js = _js(name)
    assert "loginRetryTimer" in js, f"{name} 缺重试定时器句柄"
    assert "clearLoginRetryTimer" in js, f"{name} 缺清定时器 helper"
    assert "clearTimeout(state.loginRetryTimer)" in js, f"{name} 未清句柄"
    assert "if (!state.loginRetryTimer)" in js, f"{name} 调度前须判无挂起定时器"
    assert "state.loginRetryTimer = setTimeout" in js, f"{name} 句柄须存入 state"


def test_workbench_ctrl_k_prefill_syncs_send_button():
    # MF-2：Ctrl+K 预填 "/" 后发送按钮须同步可用。
    js = _js("workbench.js")
    assert 'target.value = "/";\n            renderSug();\n            syncCmdGoDisabled();' in js


@pytest.mark.parametrize("name", ["mobile.js", "workbench.js"])
def test_frontend_no_raw_backend_error_on_screen(name):
    js = _js(name)
    raw_sites = [
        'pushFeed("敕令失败：" + data.error',
        '"敕令失败：" + e.message',
        "toast(e.message",
        "toast(err.message",
        '"传音失败：" + e.message',
        'chatMsg("", data.error',
        'chatMsgM("", data.error',
        "data.text || data.error",
        'res.error || "取回机缘受阻"',
        'data.error || data.text || "天劫狂暴',
        'a.error || "未就绪"',
        '"挖宝神识受阻：" + err.message',
        '"神识传音受阻：" + err.message',
        '"穿戴法宝神识受阻：" + err.message',
        '"卸下法宝神识受阻：" + err.message',
        '"无法连通神识：" + err.message',
        '"神识传信受阻：" + err.message',
        'chatMsg("", "传音受阻：" + e.message',
        'chatMsgM("", "传音失败：" + e.message',
    ]
    for site in raw_sites:
        assert site not in js, f"{name} 仍有后端原文原样上屏：{site}"


def test_mobile_empty_command_submit_blocked_at_trigger():
    js = _js("mobile.js")
    assert 'if (!$("cmdInput").value.trim()) return;' in js
    assert "cmdGo" in js and ".disabled = !" in js, "空指令时发送按钮须禁用"


def test_workbench_empty_command_submit_blocked_at_trigger():
    js = _js("workbench.js")
    assert "if (!val.trim()) return;" in js
    assert "cmdGo" in js and ".disabled = !" in js, "空指令时发送按钮须禁用"


@pytest.mark.parametrize("name", ["mobile.js", "workbench.js"])
def test_frontend_js_syntax(name):
    node = shutil.which("node")
    if not node:
        pytest.skip("node 不可用，跳过 JS 语法检查")
    r = subprocess.run([node, "--check", str(ROOT / "web" / name)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"{name} 语法错误：{r.stderr}"
