"""Keeps the last seen price/stock of each book in SQLite and finds what changed."""

import sqlite3
from datetime import datetime, timezone

from price_watch.scraper import Book

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    url        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    price      REAL NOT NULL,
    in_stock   INTEGER NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS price_history (
    url     TEXT NOT NULL,
    price   REAL NOT NULL,
    seen_at TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def record(conn: sqlite3.Connection, books: list[Book],
           min_drop: float = 0.01) -> list[dict]:
    """Saves the books and returns the changes worth telling someone about.

    A brand new book is not a change: the first run would spam every book.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    changes = []
    with conn:
        for book in books:
            old = conn.execute("SELECT * FROM books WHERE url = ?", (book.url,)).fetchone()
            base = {"url": book.url, "title": book.title, "price": book.price}
            if old is None:
                conn.execute(
                    "INSERT INTO books VALUES (?, ?, ?, ?, ?, ?)",
                    (book.url, book.title, book.price, int(book.in_stock), now, now))
                conn.execute("INSERT INTO price_history VALUES (?, ?, ?)",
                             (book.url, book.price, now))
                continue
            if old["price"] - book.price >= min_drop:
                changes.append({**base, "kind": "price_drop", "old_price": old["price"]})
            if book.in_stock and not old["in_stock"]:
                changes.append({**base, "kind": "back_in_stock"})
            if book.price != old["price"]:
                conn.execute("INSERT INTO price_history VALUES (?, ?, ?)",
                             (book.url, book.price, now))
            conn.execute(
                "UPDATE books SET title = ?, price = ?, in_stock = ?, last_seen = ? WHERE url = ?",
                (book.title, book.price, int(book.in_stock), now, book.url))
    return changes


def history(conn: sqlite3.Connection, url: str) -> list[dict]:
    rows = conn.execute(
        "SELECT price, seen_at FROM price_history WHERE url = ? ORDER BY seen_at", (url,))
    return [dict(r) for r in rows]
