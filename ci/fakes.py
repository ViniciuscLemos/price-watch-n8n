"""Pretends to be Steam (store, api and community), Discord, ntfy and CallMeBot in CI.

The Steam endpoints answer from the test fixtures (prices, a wishlist) and the
watchlist (names), so the e2e run doesn't depend on Steam being up or on real sales.
Everything the senders deliver is appended to /out/messages.txt.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PRICES = json.load(open("/fixtures/prices.json", encoding="utf-8"))
NAMES = {str(g["appid"]): g["name"] for g in json.load(open("/watchlist.json", encoding="utf-8"))}
WISHLIST = json.load(open("/fixtures/wishlist.json", encoding="utf-8"))


def save(line: str):
    with open("/out/messages.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, payload=None):
        body = json.dumps(payload).encode() if payload is not None else b""
        self.send_response(status)
        # an empty body marked as json makes n8n's http node fail, like a real 204 wouldn't
        if payload is not None:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/appdetails":
            ids = query["appids"].split(",")
            return self.reply(200, {i: PRICES.get(i, {"success": False}) for i in ids})
        if url.path == "/IStoreBrowseService/GetItems/v1/":
            ids = [str(i["appid"]) for i in json.loads(query["input_json"])["ids"]]
            items = [{"success": 1, "appid": int(i), "name": NAMES.get(i, f"Game {i}"),
                      "assets": {"asset_url_format": f"steam/apps/{i}/${{FILENAME}}", "header": "header.jpg"}}
                     for i in ids]
            return self.reply(200, {"response": {"store_items": items}})
        if url.path == "/id/ci-profile/":
            body = b"<profile><steamID64>76561198000000001</steamID64></profile>"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if url.path == "/IWishlistService/GetWishlist/v1/":
            return self.reply(200, WISHLIST)
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
