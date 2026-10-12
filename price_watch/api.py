"""Small HTTP API that n8n calls on a schedule."""

import os

from flask import Flask, jsonify, request

from price_watch import scraper, store


def create_app(db_path: str | None = None, scrape=scraper.scrape) -> Flask:
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
        start_url = body.get("url", scraper.BASE_URL)
        if not isinstance(start_url, str) or not start_url.startswith(scraper.BASE_URL):
            # it's a public endpoint inside docker, so no scraping random sites
            return {"error": f"only {scraper.BASE_URL} is allowed"}, 400
        try:
            pages = max(1, min(int(body.get("pages", 3)), 50))
        except (TypeError, ValueError):
            return {"error": "pages must be a number"}, 400

        books = scrape(start_url, max_pages=pages)
        conn = store.connect(db_path)
        try:
            changes = store.record(conn, books)
        finally:
            conn.close()
        return jsonify(checked=len(books), changes=changes)

    @app.get("/history")
    def history():
        url = request.args.get("url", "")
        conn = store.connect(db_path)
        try:
            return jsonify(url=url, prices=store.history(conn, url))
        finally:
            conn.close()

    return app


app = create_app()
