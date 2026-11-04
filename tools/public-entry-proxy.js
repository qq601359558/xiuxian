// 单入口代理：给公网隧道/部署用的同源入口。
// 静态托管仓库 web/；游戏接口反向代理到本机游戏服 127.0.0.1:8765。
// 用法：先起游戏服（python -m server.run），再 node tools/public-entry-proxy.js [port]（默认 8080），
// 最后把隧道指到本代理：ngrok http 8080 或 cloudflared tunnel --url http://127.0.0.1:8080。
// 玩家打开隧道给的公网地址即可玩（web/app.js 在非本机源下默认同源连接，无需手填服地址）。
"use strict";
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = Number(process.argv[2] || 8080);
const WEB_ROOT = path.join(__dirname, "..", "web");
const GAME_HOST = "127.0.0.1";
const GAME_PORT = 8765;

const API = (p) =>
  p === "/health" || p === "/register" || p === "/login" || p === "/join" ||
  p === "/logout" || p === "/action" || p === "/who" || p === "/ailog" ||
  p === "/briefing" || p.startsWith("/world/");

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".txt": "text/plain; charset=utf-8",
};

const server = http.createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const p = url.pathname;
  if (API(p)) {
    const proxy = http.request(
      { host: GAME_HOST, port: GAME_PORT, path: req.url, method: req.method, headers: { ...req.headers, host: `${GAME_HOST}:${GAME_PORT}` } },
      (up) => { res.writeHead(up.statusCode, up.headers); up.pipe(res); }
    );
    proxy.on("error", (e) => {
      console.error("proxy error", p, e.message);
      if (!res.headersSent) res.writeHead(502, { "content-type": "application/json" });
      res.end(JSON.stringify({ ok: false, error: "game server unreachable" }));
    });
    req.pipe(proxy);
    return;
  }
  let file = p === "/" ? "/index.html" : decodeURIComponent(p);
  const full = path.normalize(path.join(WEB_ROOT, file));
  if (!full.startsWith(WEB_ROOT)) { res.writeHead(403); return res.end("forbidden"); }
  fs.readFile(full, (err, data) => {
    if (err) { res.writeHead(404, { "content-type": "text/plain" }); return res.end("not found"); }
    res.writeHead(200, { "content-type": TYPES[path.extname(full)] || "application/octet-stream" });
    res.end(data);
  });
});

server.listen(PORT, "127.0.0.1", () => console.log(`single-entry proxy listening on 127.0.0.1:${PORT}`));
