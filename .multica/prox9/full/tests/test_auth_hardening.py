"""PROX-9 authentication and static-file security regressions."""
import http.client
import json
import sqlite3
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


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
    (tmp_path / ".env").write_bytes(b"LLM_API_KEY=security-test-secret")
    (tmp_path / "data" / "tiandao.db").write_bytes(b"SQLite format 3\x00private-save")
    (tmp_path / "web" / "leak.db").write_bytes(b"SQLite format 3\x00private-save")
    for filename in ("index.html", "workbench.css", "workbench.js", "app.css", "app.js", "style.css"):
        (tmp_path / "web" / filename).write_text("public " + filename, encoding="utf-8")
    for suffix in ("json", "svg", "jpg", "jpeg", "png", "webp", "gif"):
        (tmp_path / "web" / "images" / ("sample." + suffix)).write_bytes(b"public-image")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), app.GameHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def request(method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", httpd.server_port, timeout=15)
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        try:
            connection.request(
                method, path,
                body=json.dumps(payload).encode("utf-8") if payload is not None else None,
                headers=request_headers,
            )
            response = connection.getresponse()
            return response.status, response.read(), response.getheader("Content-Type")
        finally:
            connection.close()

    try:
        yield SimpleNamespace(
            request=request, world=world, root=tmp_path,
            db_path=tmp_path / "world.db", base=f"http://127.0.0.1:{httpd.server_port}",
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _post(api, path, payload):
    status, body, _content_type = api.request("POST", path, payload)
    return status, json.loads(body)


def _register(api, username="security_user", name="同名修士"):
    status, result = _post(api, "/register", {
        "username": username, "password": "secret123", "name": name,
    })
    assert status == 200 and result["ok"] is True
    return result


def _snapshot(api):
    with sqlite3.connect(api.db_path) as connection:
        characters = connection.execute(
            "SELECT id, user_id, name, data_json, updated_at FROM characters ORDER BY id"
        ).fetchall()
        sessions = connection.execute("SELECT * FROM auth_sessions ORDER BY token").fetchall()
    return characters, sessions, dict(api.world.sessions)


@pytest.mark.parametrize("path", [
    "/web/../.env", "/web/../data/tiandao.db", "/web/..%2f.env", "/web/....//.env",
    "/web/%2e%2e%2f.env", "/web/%252e%252e%252f.env",
    "/web/./index.html", "/web//index.html", "/web/images//sample.png",
    "/web/%25252e%25252e%25252f.env", "/web/..%5c.env", "/web/..%255c.env",
    "/images/../../.env", "/web/leak.db", "/web/index.html%00", "/.env", "/config.py",
])
def test_static_rejects_traversal_and_private_files(api, path):
    status, body, _content_type = api.request("GET", path)
    assert status == 404
    assert b"security-test-secret" not in body
    assert b"SQLite format 3" not in body
    assert b"private-save" not in body


@pytest.mark.parametrize("path, mime", [
    ("/", "text/html"), ("/index.html", "text/html"), ("/web", "text/html"),
    ("/web/", "text/html"), ("/web/index.html", "text/html"),
    ("/workbench.css", "text/css"), ("/workbench.js", "text/javascript"),
    ("/app.css", "text/css"), ("/app.js", "text/javascript"), ("/style.css", "text/css"),
    ("/web/images/sample.json", "application/json"), ("/web/images/sample.svg", "image/svg+xml"),
    ("/web/images/sample.jpg", "image/jpeg"), ("/web/images/sample.jpeg", "image/jpeg"),
    ("/web/images/sample.png", "image/png"), ("/web/images/sample.webp", "image/webp"),
    ("/web/images/sample.gif", "image/gif"), ("/images/sample.png", "image/png"),
])
def test_static_public_resources_remain_available(api, path, mime):
    status, body, content_type = api.request("GET", path)
    assert status == 200 and body.startswith(b"public")
    assert content_type.startswith(mime)


def test_root_resource_fallback_is_explicit(api):
    (api.root / "web" / "workbench.css").unlink()
    (api.root / "workbench.css").write_bytes(b"explicit-root-style")
    status, body, _content_type = api.request("GET", "/workbench.css")
    assert status == 200 and body == b"explicit-root-style"


@pytest.mark.parametrize("path, relative", [
    ("/web/linked.js", "web/linked.js"), ("/images/linked.js", "web/images/linked.js"),
    ("/workbench.js", "workbench.js"),
])
def test_resolved_file_cannot_escape_allowed_root(api, monkeypatch, path, relative):
    target = api.root / relative
    if relative == "workbench.js":
        (api.root / "web" / "workbench.js").unlink()
    target.write_bytes(b"public-link-placeholder")
    secret = api.root / "private.js"
    secret.write_bytes(b"security-test-secret")
    original_resolve = Path.resolve

    def resolve(candidate, *args, **kwargs):
        if candidate == target:
            return secret
        return original_resolve(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    status, body, _content_type = api.request("GET", path)
    assert status == 404 and b"security-test-secret" not in body


@pytest.mark.parametrize("payload", [
    {}, {"name": "同名修士"}, {"user_id": "victim_uid"},
    {"name": "同名修士", "user_id": "victim_uid"}, {"token": ""},
])
def test_join_requires_credentials_without_side_effects(api, payload):
    victim = _register(api)
    payload = dict(payload)
    if "user_id" in payload:
        payload["user_id"] = victim["user_id"]
    before = _snapshot(api)
    status, result = _post(api, "/join", payload)
    assert status == 401 and result["code"] == "AUTH_REQUIRED"
    assert result["ok"] is False and "token" not in result
    assert _snapshot(api) == before


@pytest.mark.parametrize("path", ["/join", "/login"])
@pytest.mark.parametrize("credentials", [
    {"username": "security_user", "password": "wrong-secret"},
    {"username": "missing_user", "password": "wrong-secret"},
    {"username": "security_user", "password": {"invalid": True}},
    {"username": ["security_user"], "password": "secret123"},
])
def test_failed_credentials_are_uniform_and_never_create_characters(api, path, credentials):
    _register(api)
    before = _snapshot(api)
    status, result = _post(api, path, {"name": "同名修士", **credentials})
    assert status == 401 and result["code"] == "AUTH_FAILED"
    assert result["error"] == "账号或密匙有误"
    assert result["ok"] is False and "token" not in result
    assert _snapshot(api) == before
    assert "wrong-secret" not in (api.root / "server.log").read_text(encoding="utf-8")


def test_valid_token_resumes_after_memory_clear_and_can_act(api):
    victim = _register(api)
    api.world.sessions.clear()
    status, result = _post(api, "/join", {"token": victim["token"], "user_id": "other_uid"})
    assert status == 200 and result["character_id"] == victim["character_id"]
    assert result["user_id"] == victim["user_id"] and result["resumed"] is True
    action_status, action = _post(api, "/action", {"token": result["token"], "command": "/look"})
    assert action_status == 200 and action["ok"] is True
    assert action["status"]["name"] == victim["name"]


def test_invalid_token_does_not_fall_back_to_credentials(api):
    _register(api)
    before = _snapshot(api)
    status, result = _post(api, "/join", {
        "token": "invalid-session-secret", "username": "security_user", "password": "secret123",
    })
    assert status == 401 and result["code"] == "AUTH_FAILED"
    assert _snapshot(api) == before
    assert "invalid-session-secret" not in (api.root / "server.log").read_text(encoding="utf-8")


def test_join_credentials_create_for_account_and_resume_on_another_device(api):
    from core.account import register
    account = register("new_account", "secret123")
    victim = _register(api)
    status, first = _post(api, "/join", {
        "username": "new_account", "password": "secret123", "name": victim["name"],
        "user_id": victim["user_id"],
    })
    assert status == 200 and first["user_id"] == account["user_id"]
    assert first["character_id"] != victim["character_id"] and first["is_new_life"] is True
    status, second = _post(api, "/join", {"username": "new_account", "password": "secret123"})
    assert status == 200 and second["character_id"] == first["character_id"]
    assert second["token"] != first["token"] and second["name"] == victim["name"]


def test_registration_with_same_display_name_never_claims_other_account(api):
    victim = _register(api)
    second = _register(api, username="other_account")
    assert second["name"] == victim["name"]
    assert second["user_id"] != victim["user_id"]
    assert second["character_id"] != victim["character_id"]


@pytest.mark.parametrize("mode", ["token", "credentials"])
def test_authenticated_dead_character_starts_new_life(api, mode):
    from core.models import CharacterStatus
    from storage.db import CharacterRepository
    victim = _register(api)
    character = api.world.get_char(victim["token"])
    character.status = CharacterStatus.DEAD
    CharacterRepository.save(character)
    payload = {"token": victim["token"]} if mode == "token" else {
        "username": "security_user", "password": "secret123",
    }
    status, result = _post(api, "/join", payload)
    assert status == 200 and result["user_id"] == victim["user_id"]
    assert result["is_new_life"] is True and result["character_id"] != victim["character_id"]


@pytest.mark.parametrize("path", ["/world/briefing", "/briefing"])
@pytest.mark.parametrize("mode", ["missing", "uid", "invalid", "bare", "valid"])
def test_briefing_requires_valid_bearer_and_ignores_query_uid(api, path, mode):
    victim = _register(api)
    headers = {}
    if mode == "uid":
        path += "?uid=" + victim["user_id"]
    elif mode in ("invalid", "bare", "valid"):
        headers["Authorization"] = {
            "invalid": "Bearer invalid-token", "bare": victim["token"],
            "valid": "Bearer " + victim["token"],
        }[mode]
    status, body, _content_type = api.request("GET", path, headers=headers)
    assert status == (200 if mode == "valid" else 401)
    if mode != "valid":
        assert json.loads(body)["ok"] is False


def test_logged_out_token_cannot_resume(api):
    victim = _register(api)
    assert _post(api, "/logout", {"token": victim["token"]})[0] == 200
    before = _snapshot(api)
    status, result = _post(api, "/join", {"token": victim["token"]})
    assert status == 401 and result["code"] == "AUTH_FAILED"
    assert _snapshot(api) == before


def test_world_join_requires_explicit_nonempty_authenticated_uid(api):
    before = _snapshot(api)
    with pytest.raises(TypeError):
        api.world.join("同名修士")
    with pytest.raises(ValueError):
        api.world.join("同名修士", user_id=" ")
    assert _snapshot(api) == before


@pytest.mark.parametrize("arguments, expected", [
    (["join", "account_name", "secret123"], {"username": "account_name", "password": "secret123"}),
    (["join", "--token", "existing-token"], {"token": "existing-token"}),
])
def test_cli_join_sends_only_credentials(monkeypatch, arguments, expected):
    import server.client as client
    requests = []
    monkeypatch.setattr(sys, "argv", ["server.client", *arguments])
    monkeypatch.setattr(client, "_post", lambda path, payload: requests.append((path, payload)) or {"ok": True})
    client.main()
    assert requests == [("/join", expected)]


def test_cli_join_prompts_for_password(monkeypatch):
    import getpass
    import server.client as client
    requests = []
    monkeypatch.setattr(sys, "argv", ["server.client", "join", "account_name"])
    monkeypatch.setattr(getpass, "getpass", lambda prompt: "secret123")
    monkeypatch.setattr(client, "_post", lambda path, payload: requests.append((path, payload)) or {"ok": True})
    client.main()
    assert requests == [("/join", {"username": "account_name", "password": "secret123"})]


def test_cli_reports_authentication_error(api, monkeypatch):
    import server.client as client
    monkeypatch.setattr(client, "BASE", api.base)
    result = client._post("/join", {"token": "bad-token"})
    assert result["ok"] is False and result["code"] == "AUTH_FAILED"
