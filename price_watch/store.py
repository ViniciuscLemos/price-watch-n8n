"""Keeps the last seen price of each game in SQLite and finds what's worth a message."""

import sqlite3
from datetime import datetime, timezone

from price_watch.steam import Game, Price, store_page

SCHEMA = """
CREATE TABLE IF NOT EXISTS games (
    appid      INTEGER PRIMARY KEY,
    name       TEXT NOT NULL,
    image      TEXT NOT NULL,
    currency   TEXT NOT NULL,
    initial    INTEGER NOT NULL,
    final      INTEGER NOT NULL,
    discount   INTEGER NOT NULL,
    lowest     INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    appid   INTEGER NOT NULL,
    final   INTEGER NOT NULL,
    seen_at TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def known(conn: sqlite3.Connection, appid: int) -> bool:
    return conn.execute("SELECT 1 FROM games WHERE appid = ?", (appid,)).fetchone() is not None


def record(conn: sqlite3.Connection, prices: list[Price], games: dict[int, Game]) -> list[dict]:
    """Saves the prices and returns the deals worth telling someone about.

    A deal is a game that got cheaper since the last check, or one already on sale
    the first time it's seen. A sale that just goes on is not news again the next
    day, otherwise the same Terraria message would show up for two weeks.
    `games` has the name and banner of games seen for the first time.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    deals = []
    with conn:
        for price in prices:
            old = conn.execute("SELECT * FROM games WHERE appid = ?", (price.appid,)).fetchone()
            if old is None:
                game = games.get(price.appid)
                if game is None:
                    continue
                conn.execute(
                    "INSERT INTO games VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (price.appid, game.name, game.image, price.currency, price.initial,
                     price.final, price.discount, price.final, now, now))
                conn.execute("INSERT INTO price_history VALUES (?, ?, ?)", (price.appid, price.final, now))
                if price.discount > 0:
                    deals.append(deal(game.name, game.image, price, old_final=price.initial, lowest=False))
                continue

            if price.final < old["final"]:
                # "lowest" means lowest since this started watching, not ever on Steam
                deals.append(deal(old["name"], old["image"], price, old_final=old["final"],
                                  lowest=price.final < old["lowest"]))
            if price.final != old["final"]:
                conn.execute("INSERT INTO price_history VALUES (?, ?, ?)", (price.appid, price.final, now))
            conn.execute(
                "UPDATE games SET currency = ?, initial = ?, final = ?, discount = ?, "
                "lowest = MIN(lowest, ?), last_seen = ? WHERE appid = ?",
                (price.currency, price.initial, price.final, price.discount, price.final, now, price.appid))
    # biggest discounts first, that's what the message should open with
    return sorted(deals, key=lambda d: (-d["discount"], d["name"]))


def deal(name: str, image: str, price: Price, old_final: int, lowest: bool) -> dict:
    return {
        "appid": price.appid,
        "name": name,
        "url": store_page(price.appid),
        "image": image,
        "currency": price.currency,
        "price": price.final,
        "old_price": old_final,
        "full_price": price.initial,
        "discount": price.discount,
        "lowest": lowest,
    }


def history(conn: sqlite3.Connection, appid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT final AS price, seen_at FROM price_history WHERE appid = ? ORDER BY seen_at, rowid", (appid,))
    return [dict(r) for r in rows]
