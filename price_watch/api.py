"""Small HTTP API that n8n calls on a schedule."""

import json
import os
from pathlib import Path

import requests
from flask import Flask, jsonify, render_template, request

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
               fetch_games=steam.fetch_games, watchlist=load_watchlist,
               fetch_wishlist=steam.fetch_wishlist, profile: str | None = None) -> Flask:
    app = Flask(__name__)
    db_path = db_path or os.getenv("DB_PATH", "price_watch.db")
    # a Steam profile (id, url or custom name) whose wishlist is watched too
    profile = profile if profile is not None else os.getenv("STEAM_PROFILE", "")

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
        warnings = []
        if appids is None:
            watched = watchlist()
            targets = {k: v for k, v in watched.items() if v}
            appids = list(watched)
            if profile:
                try:
                    appids += [a for a in fetch_wishlist(profile) if a not in watched]
                except (steam.ProfileError, requests.RequestException) as error:
                    # the list in the file still gets checked, n8n gets told why the rest didn't
                    warnings.append(f"wishlist skipped: {error}")
        elif (not isinstance(appids, list) or not appids or len(appids) > MAX_GAMES
              or not all(isinstance(a, int) and not isinstance(a, bool) and a > 0 for a in appids)):
            return {"error": f"appids must be a list of 1 to {MAX_GAMES} Steam app ids"}, 400

        conn = store.connect(db_path)
        try:
            prices = fetch_prices(appids)
            # name and banner only for games it hasn't seen yet
            unknown = [p.appid for p in prices if not store.known(conn, p.appid)]
            deals = store.record(conn, prices, fetch_games(unknown) if unknown else {}, targets)
        except requests.RequestException as error:
            # n8n shows this on the failed node, which says more than a bare 500
            return {"error": f"the Steam store didn't answer: {error}"}, 502
        finally:
            conn.close()
        return jsonify(checked=len(prices), deals=deals, warnings=warnings)

    @app.get("/")
    def page():
        conn = store.connect(db_path)
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM games ORDER BY discount DESC, name")]
            for row in rows:
                row["history"] = [h["price"] for h in store.history(conn, row["appid"])]
        finally:
            conn.close()
        targets = watchlist()
        games = []
        for row in rows:
            target = targets.get(row["appid"])
            games.append({
                **row,
                "price": row["final"],
                "url": steam.store_page(row["appid"]),
                "price_text": money(row["final"], row["currency"]),
                "full_text": money(row["initial"], row["currency"]),
                "lowest_text": money(row["lowest"], row["currency"]),
                "target_text": money(target, row["currency"]) if target else "",
                "sparkline": sparkline(row["history"]),
            })
        currency = rows[0]["currency"] if rows else "BRL"
        on_sale = sum(1 for g in games if g["discount"])
        # last_seen is ISO in UTC, so the biggest string is the latest check
        last_check = max((r["last_seen"] for r in rows), default="")[:16].replace("T", " ")
        return render_template("index.html", games=games, currency=currency, on_sale=on_sale,
                               last_check=last_check)

    # the user only picks a key, the SQL comes from here
    sorts = {"discount": "discount DESC, name", "price": "final, name", "name": "name"}

    @app.get("/games")
    def games():
        on_sale = request.args.get("on_sale", "0")
        if on_sale not in ("0", "1"):
            return {"error": "on_sale must be 0 or 1"}, 400
        sort = request.args.get("sort", "discount")
        if sort not in sorts:
            return {"error": f"sort must be one of: {', '.join(sorts)}"}, 400
        # in cents, like everything else in the API: max_price=5000 is R$ 50,00
        max_price = request.args.get("max_price", "")
        if max_price and not max_price.isdigit():
            return {"error": "max_price must be a whole number of cents"}, 400
        conn = store.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT appid, name, currency, final AS price, initial AS full_price, discount, lowest, last_seen, "
                "final <= lowest AS at_lowest "
                "FROM games WHERE (discount > 0 OR ? = '0') AND (? = '' OR final <= CAST(? AS INTEGER)) "
                f"ORDER BY {sorts[sort]}", (on_sale, max_price, max_price or "0"))
            return jsonify(games=[{**dict(r), "at_lowest": bool(r["at_lowest"])} for r in rows])
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


def money(cents: int, currency: str) -> str:
    if currency == "BRL":
        return "R$ " + f"{cents / 100:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{cents / 100:,.2f} {currency}"


def sparkline(prices: list[int], width: int = 260, height: int = 30) -> str:
    """A tiny svg line of the price history; flat when it never changed."""
    if len(prices) < 2:
        # one price is not a line yet
        return ""
    low, high = min(prices), max(prices)
    span = (high - low) or 1
    step = width / (len(prices) - 1)
    points = [(i * step, height - 3 - (p - low) / span * (height - 6)) if high != low else (i * step, height / 2)
              for i, p in enumerate(prices)]
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    x, y = points[-1]
    return (f'<svg width="{width}" height="{height}" viewBox="-3 0 {width + 6} {height}" aria-hidden="true">'
            f'<polyline points="{path}" fill="none" stroke="#66c0f4" stroke-width="2"/>'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#66c0f4"/></svg>')


app = create_app()
