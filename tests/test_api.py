from price_watch.api import create_app
from price_watch.scraper import Book

prices = {"x": 30.0}


def fake_scrape(url, max_pages):
    return [Book(url="https://books.toscrape.com/x", title="X", price=prices["x"], in_stock=True)]


def client(tmp_path):
    return create_app(str(tmp_path / "test.db"), scrape=fake_scrape).test_client()


def test_check_returns_changes_between_runs(tmp_path):
    c = client(tmp_path)
    prices["x"] = 30.0
    first = c.post("/check", json={}).get_json()
    assert first == {"checked": 1, "changes": []}

    prices["x"] = 25.0
    second = c.post("/check", json={"pages": 1}).get_json()
    assert second["changes"][0]["kind"] == "price_drop"

    hist = c.get("/history", query_string={"url": "https://books.toscrape.com/x"}).get_json()
    assert [p["price"] for p in hist["prices"]] == [30.0, 25.0]


def test_check_refuses_other_sites(tmp_path):
    res = client(tmp_path).post("/check", json={"url": "https://example.com/"})
    assert res.status_code == 400


def test_bad_pages(tmp_path):
    assert client(tmp_path).post("/check", json={"pages": "lots"}).status_code == 400


def test_url_that_is_not_a_string(tmp_path):
    assert client(tmp_path).post("/check", json={"url": 123}).status_code == 400


def test_body_that_is_not_an_object(tmp_path):
    prices["x"] = 30.0
    res = client(tmp_path).post("/check", json=[1, 2])
    assert res.status_code == 200
    assert res.get_json()["checked"] == 1
