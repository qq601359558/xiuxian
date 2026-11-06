"""
局域网多人服：标准库 HTTP JSON API（零第三方依赖）
启动：python -m server.run
"""
from __future__ import annotations

import json
import re
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

from config import AI_REQUIRED, ALLOW_LOCAL_AI, LAN_HOST, LAN_PORT, VERSION, ai_available
from core.command_catalog import all_entries
from server.world import LOCK_ACQUIRE_TIMEOUT_SECONDS, WORLD, WorldBusyError
from server.log import log_event


_ACTION_LOG_COMMANDS = frozenset(
    name.lower()
    for entry in all_entries()
    for name in (entry["cmd"], *entry["aliases"])
)

_STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}

_ROOT_STATIC_FILES = {
    "/workbench.css": "workbench.css",
    "/workbench.js": "workbench.js",
    "/app.css": "app.css",
    "/app.js": "app.js",
    "/style.css": "style.css",
    # 手机端（spec: mobile-web D5-①）：与 _STATIC_PAGES 同步加条目
    "/mobile.html": "mobile.html",
    "/mobile.js": "mobile.js",
    "/mobile.css": "mobile.css",
}


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any],
                   headers: Dict[str, str] | None = None):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    for k, v in (headers or {}).items():
        handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def _touch_login_on_session(user_id: str, result: Dict[str, Any]) -> None:
    """MF-3：仅在实际发会话（result 带非空 token）后写 accounts.last_login。

    回退快照（token 为空）与 503 繁忙路径一律不写——“繁忙即未写”。
    写失败不得影响已成功的登录响应。
    """
    try:
        if result and result.get("token"):
            from storage.db import AccountRepository

            AccountRepository.touch_login(user_id)
    except Exception:
        pass


def _busy_response(handler: BaseHTTPRequestHandler):
    """login-latency-fix §2.2.4：写路径拿不到锁的唯一出口——503 可重试错误体。

    固定体 {"ok": false, "error": "SERVER_BUSY", "message": "世界正在演化，
    请稍后重试", "retryable": true} + Retry-After: 2。发出前调用方须保证
    零写操作（“繁忙即未写”），不得附带 token、不得谎称已结算/已建角。
    """
    return _json_response(
        handler,
        503,
        {"ok": False, "error": "SERVER_BUSY", "message": "世界正在演化，请稍后重试", "retryable": True},
        headers={"Retry-After": "2"},
    )


# ---- Web 静态托管（spec: web-static-hosting）----
# 按代码自身路径定位 web/（与 data/ 的定位方式一致，与工作目录无关；Docker 中即 /app/web）
_WEB_DIR = Path(__file__).resolve().parent.parent / "web"
# 精确白名单：请求路径 → (固定文件名, Content-Type)。文件名全是常量，
# 绝不把用户请求路径拼进文件系统路径，路径穿越在构造上不可能。
_STATIC_PAGES: Dict[str, tuple[str, str]] = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/ailog.html": ("ailog.html", "text/html; charset=utf-8"),
    # 手机端（spec: mobile-web D5-①）：与 _ROOT_STATIC_FILES 同步加条目
    "/mobile.html": ("mobile.html", "text/html; charset=utf-8"),
    "/mobile.js": ("mobile.js", "text/javascript; charset=utf-8"),
    "/mobile.css": ("mobile.css", "text/css; charset=utf-8"),
}


def _static_response(handler: BaseHTTPRequestHandler, path: str) -> bool:
    """命中静态白名单则发文件并返回 True；未命中返回 False（调用方走原 404）。"""
    entry = _STATIC_PAGES.get(path)
    if entry is None:
        return False
    filename, content_type = entry
    try:
        body = (_WEB_DIR / filename).read_bytes()
    except OSError:
        return False
    handler.send_response(200)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    # 灰度期页面更新频繁，一律不缓存，避免玩家拿到旧页面
    handler.send_header("Cache-Control", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)
    return True


class GameHandler(BaseHTTPRequestHandler):
    server_version = "TiandaoLAN/0.1"

    def log_message(self, fmt, *args):  # 安静一点
        pass

    # D3.1（login-latency-fix）：捕获每次响应的状态码，供 HTTP 计时日志用。
    # 只记 method/path/status/duration_ms，绝不记请求体、token、密码、Authorization。
    def send_response(self, code, message=None):
        self._http_status = code
        super().send_response(code, message)

    def _log_http(self, method: str, t0: float) -> None:
        try:
            from urllib.parse import urlparse as _up

            path = _up(self.path).path
        except Exception:
            path = ""
        status = getattr(self, "_http_status", None)
        log_event(
            "HTTP",
            "http",
            method=method,
            path=path,
            status=status if isinstance(status, int) else 500,
            duration_ms=int((time.time() - t0) * 1000),
        )

    def do_GET(self):
        t0 = time.time()
        try:
            self._do_GET_impl()
        finally:
            self._log_http("GET", t0)

    def do_POST(self):
        t0 = time.time()
        try:
            self._do_POST_impl()
        finally:
            self._log_http("POST", t0)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _serve_static(self, path: str) -> bool:
        """只托管 web 目录与显式白名单资源。"""
        from config import BASE_DIR
        from urllib.parse import unquote

        # ---- 图库 /assets/ 专用分支（spec: gallery-gameplay §4）----
        # 置于既有分支之前：正则闸 + GALLERY_ASSET_KEYS 常量闸双闸齐过才放行，
        # 文件路径由常量相对路径拼 web/assets，绝不用请求串拼路径。
        # 任一闸不过 → 返回 False 落回既有流程（最终 404，不给探测预言机差异）。
        if path.startswith("/assets/") or path == "/assets":
            from core.gallery_assets import GALLERY_ASSET_KEYS

            decoded = path
            for decode_round in range(3):
                if not decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
                    return False
                if any(segment in ("", ".", "..") for segment in decoded[1:].split("/")):
                    return False
                if decode_round < 2:
                    decoded = unquote(decoded)
            if "%" in decoded:
                return False
            if not re.fullmatch(r"/assets/(portraits|artifacts|arts|maps)/[a-z0-9-]+\.webp", decoded):
                return False
            relative = decoded[len("/assets/"):]
            if relative not in GALLERY_ASSET_KEYS:
                return False
            assets_root = (_WEB_DIR / "assets").resolve()
            try:
                fp = (assets_root / relative).resolve()
                fp.relative_to(assets_root)
                if not fp.is_file():
                    return False
                data = fp.read_bytes()
            except (OSError, ValueError, RuntimeError):
                return False
            self.send_response(200)
            self.send_header("Content-Type", "image/webp")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            # 图库为版本内不变的静态资产：1 小时缓存（与页面 no-cache 刻意不同，§4.2）
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return True

        root = BASE_DIR.resolve()
        allowed_root = root / "web"
        if path in ("/", "/index.html", "/web", "/web/", "/web/index.html"):
            candidate = allowed_root / "index.html"
        else:
            decoded = path
            for decode_round in range(3):
                if not decoded.startswith("/") or "\\" in decoded or "\x00" in decoded:
                    return False
                if any(segment in ("", ".", "..") for segment in decoded[1:].split("/")):
                    return False
                if decode_round < 2:
                    decoded = unquote(decoded)
            if "%" in decoded:
                return False
            if decoded.startswith("/web/"):
                candidate = allowed_root / decoded[len("/web/"):]
            elif decoded.startswith("/images/"):
                allowed_root = allowed_root / "images"
                candidate = allowed_root / decoded[len("/images/"):]
            elif decoded in _ROOT_STATIC_FILES:
                filename = _ROOT_STATIC_FILES[decoded]
                candidate = allowed_root / filename
                if not candidate.is_file():
                    candidate = root / filename
                    allowed_root = None
            else:
                return False
        try:
            fp = candidate.resolve()
            if allowed_root is None:
                if fp != candidate:
                    return False
            else:
                fp.relative_to(allowed_root)
            ctype = _STATIC_CONTENT_TYPES.get(fp.suffix.lower())
            if not ctype or not fp.is_file():
                return False
            data = fp.read_bytes()
        except (OSError, ValueError, RuntimeError):
            return False
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
        return True

    def _do_GET_impl(self):
        path = urlparse(self.path).path
        if path == "/health":
            # 灰度运维自检：版本、AI 通道状态、在线会话数（字段只增不改，兼容旧探针）
            return _json_response(
                self,
                200,
                {
                    "ok": True,
                    "service": "tiandao-lan",
                    "version": VERSION,
                    "ai_available": ai_available(),
                    "ai_required": AI_REQUIRED,
                    "allow_local_ai": ALLOW_LOCAL_AI,
                    "online": len(WORLD.sessions),
                },
            )
        if self._serve_static(path):
            return
        if path == "/ailog":
            from ai.calllog import tail_ai_calls, AI_LOG_PATH

            qs = urlparse(self.path).query
            n = 50
            for part in qs.split("&"):
                if part.startswith("n="):
                    try:
                        n = max(1, min(200, int(part[2:])))
                    except ValueError:
                        pass
            rows = tail_ai_calls(n)
            return _json_response(
                self,
                200,
                {"ok": True, "count": len(rows), "path": str(AI_LOG_PATH), "items": rows},
            )
        if path == "/who":
            # 无鉴权粗览 + 江湖近况投影
            from storage.db import CharacterRepository
            from core.jianghu import list_recent, format_event_line
            alive = CharacterRepository.list_all_alive()
            feed = list_recent(limit=5)
            return _json_response(self, 200, {
                "ok": True,
                "count": len(alive),
                "players": [
                    {"id": a.id, "name": a.name, "realm": a.realm.name, "location": a.location}
                    for a in alive[:50]
                ],
                "recent_events": [
                    {
                        "event_id": e.get("id"),
                        "kind": e.get("kind"),
                        "summary": e.get("summary"),
                        "location": e.get("location"),
                        "created_at": e.get("created_at"),
                    }
                    for e in feed
                ],
                "feed_lines": [format_event_line(e) for e in feed],
            })
        if path == "/world/feed" or path.startswith("/world/feed"):
            # 江湖因果账投影：与 NPC 离线演化同一事实源
            from core.jianghu import list_recent, format_event_line

            qs = urlparse(self.path).query
            since = None
            limit = 20
            kind = None
            for part in qs.split("&"):
                if part.startswith("since="):
                    try:
                        since = float(part[6:])
                    except ValueError:
                        pass
                elif part.startswith("limit="):
                    try:
                        limit = max(1, min(100, int(part[6:])))
                    except ValueError:
                        pass
                elif part.startswith("kind="):
                    kind = part[5:] or None
            events = list_recent(limit=limit, since=since, kind=kind)
            return _json_response(self, 200, {
                "ok": True,
                "count": len(events),
                "events": events,
                "lines": [format_event_line(e) for e in events],
            })
        if path in ("/world/briefing", "/briefing"):
            from storage.db import AuthSessionRepository, CharacterRepository
            from core.briefing import briefing as build_briefing

            auth = self.headers.get("Authorization") or ""
            scheme, separator, token = auth.partition(" ")
            if scheme.lower() != "bearer" or not separator or not token.strip():
                return _json_response(self, 401, {"ok": False, "code": "AUTH_REQUIRED", "error": "需要 Bearer token"})
            sess = AuthSessionRepository.get(token.strip())
            if not sess:
                return _json_response(self, 401, {"ok": False, "code": "AUTH_FAILED", "error": "会话无效，请用账号密匙登录"})
            char = CharacterRepository.get_by_user_id(sess["user_id"])
            if not char:
                return _json_response(self, 404, {"ok": False, "error": "角色不存在"})
            b = build_briefing(char)
            return _json_response(self, 200, b)
        if path == "/world/messages":
            from core.world_channel import WorldChannel
            import time as _t

            qs = urlparse(self.path).query
            since = 0.0
            limit = 20
            for part in qs.split("&"):
                if part.startswith("since="):
                    try:
                        since = float(part[6:])
                    except ValueError:
                        pass
                if part.startswith("limit="):
                    try:
                        limit = max(1, min(50, int(part[6:])))
                    except ValueError:
                        pass
            msgs = WorldChannel.recent(limit=limit, since_ts=since)
            return _json_response(
                self,
                200,
                {
                    "ok": True,
                    "server_time": _t.time(),
                    "count": len(msgs),
                    "messages": [m.model_dump() for m in msgs],
                },
            )
        if path == "/world/director" or path.startswith("/world/director"):
            from core.world_director import director_snapshot
            from core.schedule import build_world_evolution

            try:
                snap = director_snapshot()
                evo = build_world_evolution()
                # 态势卡：director snapshot + /世情 同构 evolution
                snap["evolution"] = evo
                snap["summary_lines"] = evo.get("summary_lines") or []
            except Exception as e:
                return _json_response(self, 500, {"ok": False, "error": str(e)[:200]})
            return _json_response(self, 200, snap)
        if path == "/commands" or path.startswith("/commands"):
            from core.command_catalog import catalog_json, search_commands

            qs = urlparse(self.path).query or ""
            q = ""
            limit = 20
            for part in qs.split("&"):
                if part.startswith("q="):
                    try:
                        from urllib.parse import unquote

                        q = unquote(part[2:])
                    except Exception:
                        q = part[2:]
                elif part.startswith("limit="):
                    try:
                        limit = max(1, min(80, int(part[6:])))
                    except ValueError:
                        pass
            if q:
                return _json_response(self, 200, {"ok": True, "query": q, "commands": search_commands(q, limit=limit)})
            return _json_response(self, 200, catalog_json())
        # Web 静态托管：置于全部 API 路由之后、白名单精确匹配，API 优先级不变
        if _static_response(self, path):
            return
        return _json_response(self, 404, {"ok": False, "error": "not found"})

    def _do_POST_impl(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _json_response(self, 400, {"ok": False, "error": "invalid json"})
        if not isinstance(data, dict):
            return _json_response(self, 400, {"ok": False, "error": "需要 JSON 对象"})

        if path == "/register":
            from core.account import register as acct_register

            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            name = str(data.get("name") or username or "").strip()[:12]
            reg = acct_register(username, password, display_name=name)
            if not reg.get("ok"):
                return _json_response(self, 400, reg)
            # login-latency-fix §2.2.4：同一 2 秒总界贯穿 join；拿不到锁则
            # 503 繁忙。acct_register 刚建的账号行须回滚，否则“原样重试”
            # 会撞“用户名已存在”——繁忙即未写，重试安全。
            deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
            try:
                result = WORLD.join(name or username, user_id=reg["user_id"], _deadline=deadline)
            except WorldBusyError:
                try:
                    from storage.db import AccountRepository

                    # MF-4：delete 内含条件删除——该 uid 若已被另路建角/发会话，
                    # 返回 False 且不删行，回滚是安全的空操作。
                    AccountRepository.delete(reg["user_id"])
                except Exception:
                    pass
                return _busy_response(self)
            log_event("CMD", "register", username=username)
            return _json_response(self, 200, {"ok": True, "username": username, **result})

        if path in ("/login", "/join"):
            from core.account import login as acct_login
            from storage.db import AuthSessionRepository

            token = data.get("token") if path == "/join" else None
            if token:
                sess = AuthSessionRepository.get(token) if isinstance(token, str) else None
                if not sess:
                    log_event("GATE", "authentication_failed", route=path, reason="INVALID_TOKEN")
                    return _json_response(self, 401, {"ok": False, "code": "AUTH_FAILED", "error": "账号或密匙有误"})
                name = str(data.get("name") or sess["name"] or "散修").strip()[:12]
                deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
                try:
                    result = WORLD.join(name, user_id=sess["user_id"], auto_rebirth=(path == "/join"), _deadline=deadline)
                except WorldBusyError:
                    return _busy_response(self)
                _touch_login_on_session(sess["user_id"], result)
                log_event("CMD", "join", ok=True)
                return _json_response(self, 200, {"ok": True, **result})

            username = data.get("username") or ""
            password = data.get("password") or ""
            if path == "/join" and not username and not password:
                return _json_response(self, 401, {"ok": False, "code": "AUTH_REQUIRED", "error": "需要 token 或账号与密匙"})
            if isinstance(username, str) and isinstance(password, str):
                lg = acct_login(username, password)
            else:
                lg = {"ok": False, "error": "INVALID_CREDENTIAL_TYPES"}
            if not lg.get("ok"):
                log_event("GATE", "authentication_failed", route=path, reason=lg.get("error"))
                return _json_response(self, 401, {"ok": False, "code": "AUTH_FAILED", "error": "账号或密匙有误"})
            username = lg["username"]
            name = str(data.get("name") or username).strip()[:12]
            # 同一 2 秒总界贯穿 dead_payload + join（§2.2.4）：两步共享 deadline，
            # 避免各等 2 秒后合计超界。读路径拿不到锁走锁外回退快照（200），
            # 写路径拿不到锁抛 WorldBusyError → 503 繁忙。
            deadline = time.monotonic() + LOCK_ACQUIRE_TIMEOUT_SECONDS
            try:
                if path == "/login":
                    # account-death §2.6：现世角色已死 → 只报死讯＋钱包，不自动建角；
                    # 建角须玩家显式 /转世（token 保持有效，指向死行会话）。
                    # /join 不走此路：凭据入世即转世开新世（分支语义，见下方 join 调用）。
                    dead = WORLD.dead_payload(lg["user_id"], username=username, _deadline=deadline)
                    if dead is not None:
                        _touch_login_on_session(lg["user_id"], dead)
                        log_event("CMD", "login_dead", username=username)
                        return _json_response(self, 200, {"ok": True, "username": username, **dead})
                result = WORLD.join(name, user_id=lg["user_id"], auto_rebirth=(path == "/join"), _deadline=deadline)
            except WorldBusyError:
                return _busy_response(self)
            _touch_login_on_session(lg["user_id"], result)
            log_event("CMD", path[1:], username=username)
            return _json_response(self, 200, {"ok": True, "username": username, **result})

        if path == "/logout":
            token = str(data.get("token") or "")
            if not token:
                return _json_response(self, 400, {"ok": False, "error": "需要 token"})
            result = WORLD.logout(token)
            return _json_response(self, 200, result)

        if path == "/action":
            token = str(data.get("token") or "")
            command = str(data.get("command") or "")
            if not token or not command:
                return _json_response(self, 400, {"ok": False, "error": "需要 token 与 command"})
            command_parts = command.split(None, 1)
            command_name = command_parts[0].lower() if command_parts else ""
            if command_name and command_name not in _ACTION_LOG_COMMANDS:
                command_name = "UNKNOWN_COMMAND" if command_name.startswith("/") else "FREE_TEXT"
            try:
                log_event("CMD", "action", cmd=command_name)
                result = WORLD.handle(token, command)
                if not result.get("ok", True):
                    log_event("GATE", "action_rejected", cmd=command_name, error="ACTION_REJECTED")
            except Exception as error:
                log_event(
                    "ERROR",
                    "action_failed",
                    cmd=command_name,
                    error_type=type(error).__name__,
                    traceback=[
                        {"file": frame.filename, "line": frame.lineno, "function": frame.name}
                        for frame in traceback.extract_tb(error.__traceback__)
                    ],
                )
                return _json_response(self, 500, {
                    "ok": False,
                    "code": "ACTION_FAILED",
                    "error": "行动处理异常，请稍后重试。",
                })
            return _json_response(self, 200, result)

        if path == "/chat":
            """聊天窗 API：点名开聊 + 自由发言（无需斜杠）"""
            token = str(data.get("token") or "")
            if not token:
                return _json_response(self, 400, {"ok": False, "error": "需要 token"})
            to = str(data.get("to") or "").strip()
            text = str(data.get("text") or "").strip()
            if not to and not text:
                return _json_response(self, 400, {"ok": False, "error": "需要 to 或 text"})
            if to and text:
                cmd = f"/交谈 {to} {text}"
            elif text:
                cmd = text
            else:
                cmd = f"/交谈 {to}"
            log_event("CMD", "chat", cmd=cmd.split()[0] if cmd else "")
            result = WORLD.handle(token, cmd)
            return _json_response(self, 200, result)

        return _json_response(self, 404, {"ok": False, "error": "not found"})


def main():
    host = LAN_HOST
    port = LAN_PORT
    # 正式开服时启用后台 NPC tick
    try:
        from config import NPC_TICK_INTERVAL_SECONDS
        if NPC_TICK_INTERVAL_SECONDS > 0:
            WORLD.__dict__["_stop_tick"] = False
            import threading
            t = threading.Thread(target=WORLD._tick_loop, daemon=True)
            t.start()
            print(f"NPC 议程自动 tick：每 {NPC_TICK_INTERVAL_SECONDS:.0f} 秒")
    except Exception:
        pass

    # 开服补一轮轻量 tick（世界「闭关期间」也有动静）
    try:
        from core.npc_agenda import NpcAgendaEngine
        acted = NpcAgendaEngine.tick_world(max_npcs=3, force=False)
        if acted:
            print(f"开服 tick：{len(acted)} 名 NPC 有动向")
    except Exception:
        pass

    try:
        from core.world_channel import post_system

        post_system("boot", f"天道服已开启：{host}:{port}，诸位道友可入世。")
    except Exception:
        pass

    httpd = ThreadingHTTPServer((host, port), GameHandler)
    print(f"《天道因果录》局域网服已启动 http://{host}:{port}")
    print("接口：网页 http://%s:%s/  · 账号 POST /register /login，凭 token 续玩 /join；行动 /action /chat，退出 /logout  GET /who /health /commands /world/director" % (LAN_HOST, LAN_PORT))
    log_event("SEASON", "server_start", host=host, port=port)
    print("示例（先注册账号）：curl -X POST http://127.0.0.1:8765/login -H 'Content-Type: application/json' -d '{\"username\":\"你的账号\",\"password\":\"你的密匙\"}'")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n天道收束，正在结算世间余事……")
        try:
            WORLD.stop_tick()
        except Exception:
            pass
        # 关服前批量 tick：把「玩家不在时」的世界推完
        try:
            from core.npc_agenda import NpcAgendaEngine
            from core.memory import RevengeEngine
            from storage.db import CharacterRepository, ChronicleRepository
            acted = NpcAgendaEngine.tick_world(max_npcs=8, force=True)
            for r in acted:
                try:
                    ChronicleRepository.record(
                        "NPC", r.get("npc") or "天道",
                        (r.get("narrative") or "")[:60],
                    )
                except Exception:
                    pass
            # 少量因果回访（有账的玩家号）
            rev_n = 0
            for c in CharacterRepository.list_all_alive():
                uid = str(c.user_id)
                if uid.startswith("npc_") or uid.startswith("ai_npc_"):
                    continue
                try:
                    rv = RevengeEngine.maybe_callback(c, chance=0.4)
                    if rv:
                        rev_n += 1
                except Exception:
                    continue
            print(f"关服结算：NPC 行动 {len(acted)} 条，因果回访 {rev_n} 起")
        except Exception as e:
            print(f"关服结算异常：{e}")
        httpd.server_close()
        print("天道已收束。")


if __name__ == "__main__":
    main()
