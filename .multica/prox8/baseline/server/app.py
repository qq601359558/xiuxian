"""
局域网多人服：标准库 HTTP JSON API（零第三方依赖）
启动：python -m server.run
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import urlparse

from config import LAN_HOST, LAN_PORT
from server.world import WORLD
from server.log import log_event


def _json_response(handler: BaseHTTPRequestHandler, code: int, payload: Dict[str, Any]):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


class GameHandler(BaseHTTPRequestHandler):
    server_version = "TiandaoLAN/0.1"

    def log_message(self, fmt, *args):  # 安静一点
        pass

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _serve_static(self, path: str) -> bool:
        """托管工作台前端（web/ 与仓库根目录同名资源）"""
        from config import BASE_DIR
        from urllib.parse import unquote

        if path in ("/", "/index.html", "/web", "/web/", "/web/index.html"):
            rel = "web/index.html"
        elif path.startswith("/web/"):
            rel = "web/" + unquote(path[len("/web/"):])
        elif path.startswith("/images/"):
            rel = "web/images/" + unquote(path[len("/images/"):])
        elif path in ("/workbench.css", "/workbench.js", "/app.css", "/app.js", "/style.css"):
            fname = unquote(path.lstrip("/"))
            if (BASE_DIR / "web" / fname).is_file():
                rel = "web/" + fname
            else:
                rel = fname
        else:
            return False
        # 防路径穿越
        root = BASE_DIR.resolve()
        fp = (root / rel).resolve()
        try:
            fp.relative_to(root)
        except ValueError:
            return False
        if not fp.is_file():
            return False
        ctype = "application/octet-stream"
        if fp.suffix == ".html":
            ctype = "text/html; charset=utf-8"
        elif fp.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        elif fp.suffix == ".js":
            ctype = "text/javascript; charset=utf-8"
        elif fp.suffix == ".json":
            ctype = "application/json; charset=utf-8"
        elif fp.suffix == ".svg":
            ctype = "image/svg+xml"
        elif fp.suffix in (".jpg", ".jpeg"):
            ctype = "image/jpeg"
        elif fp.suffix == ".png":
            ctype = "image/png"
        elif fp.suffix == ".webp":
            ctype = "image/webp"
        elif fp.suffix == ".gif":
            ctype = "image/gif"
        data = fp.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)
        return True

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return _json_response(self, 200, {"ok": True, "service": "tiandao-lan"})
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
        if path.startswith("/world/briefing") or path == "/briefing":
            from storage.db import AuthSessionRepository, CharacterRepository
            from core.briefing import briefing as build_briefing

            uid = None
            auth = self.headers.get("Authorization") or ""
            token = auth.replace("Bearer ", "").strip()
            if not token:
                for part in (urlparse(self.path).query or "").split("&"):
                    if part.startswith("uid="):
                        uid = part[4:]
            else:
                try:
                    sess = AuthSessionRepository.get(token)
                    uid = sess.user_id if sess else None
                except Exception:
                    uid = None
            if not uid:
                return _json_response(self, 401, {"ok": False, "error": "需要 uid= 或 Bearer token"})
            char = CharacterRepository.get_by_user_id(uid)
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
        return _json_response(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return _json_response(self, 400, {"ok": False, "error": "invalid json"})

        if path == "/register":
            from core.account import register as acct_register

            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            name = str(data.get("name") or username or "").strip()[:12]
            reg = acct_register(username, password, display_name=name)
            if not reg.get("ok"):
                return _json_response(self, 400, reg)
            result = WORLD.join(name or username, user_id=reg["user_id"])
            log_event("CMD", "register", username=username)
            return _json_response(self, 200, {"ok": True, "username": username, **result})

        if path == "/login":
            from core.account import login as acct_login

            username = str(data.get("username") or "").strip()
            password = str(data.get("password") or "")
            name = str(data.get("name") or username or "").strip()[:12]
            lg = acct_login(username, password)
            if not lg.get("ok"):
                return _json_response(self, 400, lg)
            result = WORLD.join(name, user_id=lg["user_id"])
            log_event("CMD", "login", username=username)
            return _json_response(self, 200, {"ok": True, "username": username, **result})

        if path == "/join":
            name = str(data.get("name") or "").strip()[:12]
            if not name:
                return _json_response(self, 400, {"ok": False, "error": "需要道号 name"})
            user_id = data.get("user_id")
            result = WORLD.join(name, user_id=user_id)
            log_event("CMD", "join", name=name, ok=result.get("ok", True) or "token" in result)
            return _json_response(self, 200, {"ok": True, **result})

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
            log_event("CMD", "action", cmd=command.split()[0] if command else "")
            result = WORLD.handle(token, command)
            if not result.get("ok", True):
                log_event("GATE", "action_rejected", cmd=command[:40], error=result.get("error"))
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
    print("接口：网页 http://%s:%s/  · API POST /register /login /join /action /chat /logout  GET /who /health /commands /world/director" % (LAN_HOST, LAN_PORT))
    log_event("SEASON", "server_start", host=host, port=port)
    print("示例：curl -X POST http://127.0.0.1:8765/join -d '{\"name\":\"厉飞雨\"}'")
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
