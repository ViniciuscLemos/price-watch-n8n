"""Small HTTP API that n8n calls on a schedule."""

import json
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

from price_watch import steam, store

WATCHLIST = Path(os.getenv("WATCHLIST", Path(__file__).parents[1] / "watchlist.json"))
MAX_GAMES = 100


def load_watchlist(path: Path = WATCHLIST) -> dict[int, int | None]:
    """The games to watch, each with its target price in cents (None when it has none).

    In the file the target is in the store's currency, like "target": 39.90.
    """
    games = {}
    for entry in json.loads(path.read_text("utf-8")):
        target = entry.get("target")
        if target is not None and (not isinstance(target, (int, float)) or target <= 0):
            raise ValueError(f"target for {entry['appid']} must be a positive price, got {target!r}")
        games[int(entry["appid"])] = round(target * 100) if target else None
    return games


def create_app(db_path: str | None = None, fetch_prices=steam.fetch_prices,
               fetch_game=steam.fetch_game, watchlist=load_watchlist) -> Flask:
    app = Flask(__name__)
    db_path = db_path or os.getenv("DB_PATH", "price_watch.db")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/check")
    def check():
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            # a json list or string here used to crash with a 500
            body = {}
        appids = body.get("appids")
        targets = {}
        if appids is None:
            watched = watchlist()
            targets = {k: v for k, v in watched.items() if v}
            appids = list(watched)
        elif (not isinstance(appids, list) or not appids or len(appids) > MAX_GAMES
              or not all(isinstance(a, int) and not isinstance(a, bool) and a > 0 for a in appids)):
            return {"error": f"appids must be a list of 1 to {MAX_GAMES} Steam app ids"}, 400

        conn = store.connect(db_path)
        try:
            prices = fetch_prices(appids)
            # name and banner only for games it hasn't seen yet: one extra call each
            new = {p.appid: fetch_game(p.appid) for p in prices if not store.known(conn, p.appid)}
            deals = store.record(conn, prices, {k: v for k, v in new.items() if v}, targets)
        except requests.RequestException as error:
            # n8n shows this on the failed node, which says more than a bare 500
            return {"error": f"the Steam store didn't answer: {error}"}, 502
        finally:
            conn.close()
        return jsonify(checked=len(prices), deals=deals)

    @app.get("/games")
    def games():
        conn = store.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT appid, name, currency, final AS price, initial AS full_price, discount, lowest, last_seen "
                "FROM games ORDER BY discount DESC, name")
            return jsonify(games=[dict(r) for r in rows])
        finally:
            conn.close()

    @app.get("/history")
    def history():
        appid = request.args.get("appid", "")
        if not appid.isdigit():
            # an empty list here looked like "never seen", which hid typos in the query
            return {"error": "appid is required"}, 400
        conn = store.connect(db_path)
        try:
            return jsonify(appid=int(appid), prices=store.history(conn, int(appid)))
        finally:
            conn.close()

    return app


app = create_app()
