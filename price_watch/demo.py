"""Fakes some old prices in the database so the next /check has something to report.

books.toscrape.com never changes its prices (it's a static practice site), so
without this the workflow would run forever and never send anything.

    python -m price_watch.demo [how_many]
"""

import os
import random
import sys

from price_watch import store


def make_changes(conn, how_many: int = 3, seed: int | None = None) -> list[str]:
    rng = random.Random(seed)
    urls = [r["url"] for r in conn.execute("SELECT url FROM books")]
    picked = rng.sample(urls, min(how_many, len(urls)))
    with conn:
        for i, url in enumerate(picked):
            if i % 2 == 0:
                conn.execute("UPDATE books SET price = ROUND(price + 5, 2) WHERE url = ?", (url,))
            else:
                conn.execute("UPDATE books SET in_stock = 0 WHERE url = ?", (url,))
    return picked


if __name__ == "__main__":
    conn = store.connect(os.getenv("DB_PATH", "price_watch.db"))
    picked = make_changes(conn, int(sys.argv[1]) if len(sys.argv) > 1 else 3)
    if not picked:
        print("database is empty, call /check once first")
    for url in picked:
        print("changed", url)
