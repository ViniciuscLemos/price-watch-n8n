"""Pretends to be the Steam store, Discord, ntfy and CallMeBot in CI.

GET /api/appdetails answers from the test fixtures (prices) and the watchlist
(names), so the e2e run doesn't depend on Steam being up or on real sales.
Everything the senders deliver is appended to /out/messages.txt.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PRICES = json.load(open("/fixtures/prices.json", encoding="utf-8"))
NAMES = {str(g["appid"]): g["name"] for g in json.load(open("/watchlist.json", encoding="utf-8"))}


def save(line: str):
    with open("/out/messages.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/appdetails":
            ids = query["appids"].split(",")
            if query.get("filters") == "basic":
                appid = ids[0]
                data = {"name": NAMES.get(appid, f"Game {appid}"),
                        "header_image": f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{appid}/header.jpg"}
                return self.reply(200, {appid: {"success": True, "data": data}})
            return self.reply(200, {i: PRICES.get(i, {"success": False}) for i in ids})
        if url.path == "/whatsapp.php":
            save("whatsapp " + json.dumps(query, ensure_ascii=False))
            return self.reply(200, {})
        if url.path == "/health":
            return self.reply(200, {"ok": True})
        self.reply(404, {})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        save(self.path.strip("/").split("/")[0] + " " + body)
        # Discord answers 204 with no body; ntfy answers with the message as json
        if self.path.startswith("/discord"):
            return self.reply(204)
        self.reply(200, {"id": "ci", "event": "message"})

    def log_message(self, *args):
        pass


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
