"""Independent PROX-9 QA probes against a live 127.0.0.1:8899 server."""
import json
import socket
import sqlite3
import sys
import urllib.request
import urllib.error

HOST, PORT = "127.0.0.1", 8899
BASE = f"http://{HOST}:{PORT}"
DB = r"D:\codex\xiuxian\.multica\qa\probe2\data\tiandao.db"
SECRET_MARKERS = [b"QA_PROBE_SECRET_7f3a", b"QA_PROBE_DB_7f3a",
                  b"QA_PROBE_PRIVATE_SAVE", b"SQLite format 3"]

fails = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ((" | " + detail) if detail else ""))
    if not cond:
        fails.append(name + " | " + detail)


def raw_get(target):
    """Send the request-target byte-for-byte; never let a client normalize it."""
    s = socket.create_connection((HOST, PORT), timeout=10)
    try:
        s.sendall(f"GET {target} HTTP/1.1\r\nHost: {HOST}\r\nConnection: close\r\n\r\n".encode("latin-1"))
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
        data = b"".join(chunks)
    finally:
        s.close()
    head, _, body = data.partition(b"\r\n\r\n")
    status = int(head.split(b" ")[1])
    ctype = ""
    for line in head.split(b"\r\n")[1:]:
        if line.lower().startswith(b"content-type:"):
            ctype = line.split(b":", 1)[1].strip().decode()
    return status, body, ctype


def post(path, payload):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def get(path, headers=None):
    req = urllib.request.Request(BASE + path, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Content-Type")


def snapshot():
    con = sqlite3.connect(DB)
    try:
        chars = con.execute("SELECT id,user_id,name,data_json,updated_at FROM characters ORDER BY id").fetchall()
        sessions = con.execute("SELECT token,user_id,character_id,name FROM auth_sessions ORDER BY token").fetchall()
        return chars, sessions
    finally:
        con.close()


print("=== A. static traversal / private file reads (raw request-target) ===")
traversal = [
    "/web/../.env", "/web/../data/tiandao.db", "/web/..%2f.env", "/web/....//.env",
    "/web/%2e%2e%2f.env", "/web/%252e%252e%252f.env", "/web/%25252e%25252e%25252f.env",
    "/web/..%5c.env", "/web/..%255c.env", "/web/..%2F%2E%2E%2F.env",
    "/images/../../.env", "/web/leak.db", "/web/index.html%00", "/.env", "/config.py",
    "/web/./index.html", "/web//index.html", "/web/images/../images/portrait.jpg",
]
for t in traversal:
    status, body, _ = raw_get(t)
    leaked = [m.decode() for m in SECRET_MARKERS if m in body]
    check(f"traversal {t} -> 4xx & no secret", 400 <= status < 500 and not leaked,
          f"status={status} leaked={leaked}")

print("\n=== B. legit static resources still served with correct MIME ===")
legit = [
    ("/", "text/html"), ("/index.html", "text/html"), ("/web", "text/html"), ("/web/", "text/html"),
    ("/workbench.css", "text/css"), ("/workbench.js", "text/javascript"),
    ("/app.js", "text/javascript"), ("/style.css", "text/css"),
    ("/web/index.html", "text/html"), ("/web/style.css", "text/css"),
    ("/images/portrait.jpg", "image/jpeg"), ("/web/images/portrait.jpg", "image/jpeg"),
    ("/web/images/cultivator_meditating.png", "image/png"),
    ("/images/realm_1.jpg", "image/jpeg"),
]
for t, mime in legit:
    status, body, ctype = raw_get(t)
    check(f"static {t} -> 200 {mime}", status == 200 and len(body) > 0 and (ctype or "").startswith(mime),
          f"status={status} ctype={ctype} len={len(body)}")
status, body, _ = raw_get("/workbench.css?v=123")
check("static query-string form /workbench.css?v=123 -> 200", status == 200, f"status={status}")
status, body, _ = raw_get("/app.css")
check("missing /app.css -> 404 (no phantom file)", 400 <= status < 500, f"status={status}")

print("\n=== C. /join authentication, D-5 / D-5b closure, zero side effects ===")
reg = post("/register", {"username": "qa_probe_acct", "password": "qa_secret_123", "name": "探查修士"})
check("register -> 200", reg[0] == 200 and reg[1].get("ok"), str(reg))
victim = reg[1]
uid = victim.get("user_id")
tok = victim.get("token")
char_id = victim.get("character_id")

for label, payload in [
    ("empty body", {}),
    ("bare name only", {"name": "探查修士"}),
    ("client-declared user_id", {"user_id": uid}),
    ("name + client user_id", {"name": "探查修士", "user_id": uid}),
    ("empty token", {"token": ""}),
]:
    before = snapshot()
    status, res = post("/join", payload)
    after = snapshot()
    check(f"D-5b join {label} -> 401 AUTH_REQUIRED, no token, zero side effects",
          401 == status and res.get("code") == "AUTH_REQUIRED" and res.get("ok") is False
          and "token" not in res and before == after,
          f"status={status} res={res} snapshot_same={before == after}")

before = snapshot()
status, res = post("/join", {"name": "探查修士", "user_id": uid, "username": "qa_probe_acct", "password": "wrong"})
after = snapshot()
check("wrong password on existing account -> 401 AUTH_FAILED, uniform text, no new char/session",
      401 == status and res.get("code") == "AUTH_FAILED" and res.get("error") == "账号或密匙有误"
      and before == after, f"status={status} res={res} same={before == after}")

status, res = post("/join", {"username": "no_such_account_xyz", "password": "whatever"})
check("unknown account -> 401 AUTH_FAILED (no user enumeration)",
      401 == status and res.get("code") == "AUTH_FAILED" and res.get("error") == "账号或密匙有误",
      f"status={status} res={res}")

status, res = post("/join", {"token": "not-a-real-token", "username": "qa_probe_acct", "password": "qa_secret_123"})
check("invalid token + valid creds -> 401 (no silent downgrade)",
      status == 401 and res.get("code") == "AUTH_FAILED", f"status={status} res={res}")

status, res = post("/join", {"token": tok})
check("token resume -> 200 same character", status == 200 and res.get("character_id") == char_id
      and res.get("user_id") == uid and res.get("resumed") is True, f"status={status} res={res}")
token2 = res.get("token")

status, act = post("/action", {"token": token2, "command": "/look"})
check("token resume -> /action /look works", status == 200 and act.get("ok") is True, str(act)[:200])

status, res = post("/join", {"username": "qa_probe_acct", "password": "qa_secret_123", "name": "换个道号"})
check("cross-device account login -> same character, name unchanged",
      status == 200 and res.get("character_id") == char_id and res.get("name") == "探查修士",
      f"status={status} res={res}")

status, res = post("/join", {"username": "qa_probe_acct", "password": "qa_secret_123", "user_id": "acct_deadbeef1234"})
check("client-supplied user_id ignored on credential join",
      status == 200 and res.get("user_id") == uid and res.get("character_id") == char_id,
      f"status={status} res={res}")

reg2 = post("/register", {"username": "qa_probe_other", "password": "qa_secret_456", "name": "探查修士"})
check("same display name, different account -> separate character",
      reg2[0] == 200 and reg2[1].get("character_id") != char_id and reg2[1].get("user_id") != uid,
      str(reg2)[:300])
status, res = post("/join", {"name": "探查修士"})
check("bare name still cannot claim either same-named character", status == 401, f"status={status}")

print("\n=== D. /world/briefing & /briefing Bearer-only (D-4b) ===")
for path in ("/world/briefing", "/briefing"):
    st, body, _ = get(path)
    check(f"{path} no auth -> 401", st == 401, f"status={st}")
    st, body, _ = get(path + "?uid=" + uid)
    check(f"{path} ?uid= -> 401 (no query bypass)", st == 401, f"status={st}")
    st, body, _ = get(path, {"Authorization": tok})
    check(f"{path} bare token (no Bearer) -> 401", st == 401, f"status={st}")
    st, body, _ = get(path, {"Authorization": "Bearer invalid-xyz"})
    check(f"{path} invalid Bearer -> 401", st == 401, f"status={st}")
    st, body, _ = get(path, {"Authorization": "Bearer " + tok})
    check(f"{path} valid Bearer -> 200 own briefing", st == 200, f"status={st}")

print("\n=== E. logout revokes resume ===")
st, res = post("/logout", {"token": tok})
check("logout -> 200", st == 200, f"status={st}")
before = snapshot()
st, res = post("/join", {"token": tok})
after = snapshot()
check("logged-out token cannot resume -> 401, zero side effects",
      st == 401 and before == after, f"status={st} same={before == after}")

print("\n=== SUMMARY ===")
print(f"{'ALL PASS' if not fails else str(len(fails)) + ' FAILURES'}")
for f in fails:
    print("  -", f)
sys.exit(1 if fails else 0)
