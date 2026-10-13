"""Makes some games look pricier in the database so the next /check has deals to report.

Real sales come and go on their own, but waiting for one to test the workflow
takes days, so this fakes "it was more expensive yesterday".

    python -m price_watch.demo [how_many]
"""

import os
import random
import sys

from price_watch import store


def make_changes(conn, how_many: int = 3, seed: int | None = None) -> list[int]:
    rng = random.Random(seed)
    appids = [r["appid"] for r in conn.execute("SELECT appid FROM games ORDER BY appid")]
    picked = rng.sample(appids, min(how_many, len(appids)))
    with conn:
        for appid in picked:
            # as if yesterday it cost 20% more (whole cents, the API never sends fractions)
            conn.execute("UPDATE games SET final = final * 6 / 5, lowest = final * 6 / 5 WHERE appid = ?", (appid,))
    return picked


if __name__ == "__main__":
    conn = store.connect(os.getenv("DB_PATH", "price_watch.db"))
    picked = make_changes(conn, int(sys.argv[1]) if len(sys.argv) > 1 else 3)
    if not picked:
        print("database is empty, call /check once first")
    for appid in picked:
        print("made pricier:", appid)
