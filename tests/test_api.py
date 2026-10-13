import pytest
import requests

from price_watch.api import create_app, load_watchlist
from price_watch import steam
from price_watch.steam import Game, Price

prices = {1174180: 29990}
calls = {"game": 0}


def fake_prices(appids):
    return [Price(a, "BRL", 29990, prices.get(a, 29990), 0 if prices.get(a, 29990) == 29990 else 75)
            for a in appids]


def fake_games(appids):
    calls["game"] += 1
    return {a: Game(a, f"Game {a}", "") for a in appids}


def client(tmp_path):
    return create_app(str(tmp_path / "test.db"), fetch_prices=fake_prices, fetch_games=fake_games,
                      watchlist=lambda: {1174180: None}).test_client()


def test_check_returns_deals_between_runs(tmp_path):
    c = client(tmp_path)
    prices[1174180] = 29990
    calls["game"] = 0
    assert c.post("/check", json={}).get_json() == {"checked": 1, "deals": [], "warnings": []}

    prices[1174180] = 7497
    (deal,) = c.post("/check").get_json()["deals"]
    assert (deal["name"], deal["price"], deal["discount"]) == ("Game 1174180", 7497, 75)
    # the name is only looked up the first time
    assert calls["game"] == 1

    hist = c.get("/history", query_string={"appid": 1174180}).get_json()
    assert [p["price"] for p in hist["prices"]] == [29990, 7497]
    assert c.get("/games").get_json()["games"][0]["lowest"] == 7497


def test_check_takes_its_own_list(tmp_path):
    res = client(tmp_path).post("/check", json={"appids": [10, 20]})
    assert res.get_json()["checked"] == 2


def test_bad_appids(tmp_path):
    c = client(tmp_path)
    for bad in ("1174180", [], ["x"], [True], [-1], list(range(1, 200))):
        assert c.post("/check", json={"appids": bad}).status_code == 400, bad


def test_body_that_is_not_an_object(tmp_path):
    res = client(tmp_path).post("/check", json=[1, 2])
    assert res.status_code == 200
    assert res.get_json()["checked"] == 1


def test_history_needs_an_appid(tmp_path):
    c = client(tmp_path)
    assert c.get("/history").status_code == 400
    assert c.get("/history", query_string={"appid": "elden"}).status_code == 400


def test_the_watchlist_in_the_repo_loads():
    assert len(load_watchlist()) >= 10


def test_watchlist_targets_are_in_cents(tmp_path):
    path = tmp_path / "w.json"
    path.write_text('[{"appid": 1, "target": 39.9}, {"appid": 2}]')
    assert load_watchlist(path) == {1: 3990, 2: None}
    path.write_text('[{"appid": 1, "target": "cheap"}]')
    with pytest.raises(ValueError):
        load_watchlist(path)


def test_target_from_the_watchlist(tmp_path):
    app = create_app(str(tmp_path / "t.db"), fetch_prices=fake_prices, fetch_games=fake_games,
                     watchlist=lambda: {1174180: 30000})
    prices[1174180] = 29990
    (deal,) = app.test_client().post("/check").get_json()["deals"]
    assert deal["below_target"] is True


def test_steam_down_is_a_502(tmp_path):
    def down(appids):
        raise requests.ConnectionError("no route to store.steampowered.com")

    app = create_app(str(tmp_path / "d.db"), fetch_prices=down, fetch_games=fake_games, watchlist=lambda: {1: None})
    res = app.test_client().post("/check")
    assert res.status_code == 502
    assert "Steam store didn't answer" in res.get_json()["error"]


def test_wishlist_games_are_checked_too(tmp_path):
    app = create_app(str(tmp_path / "w.db"), fetch_prices=fake_prices, fetch_games=fake_games,
                     watchlist=lambda: {1174180: None}, profile="vini",
                     fetch_wishlist=lambda profile: [1174180, 1030300])
    assert app.test_client().post("/check").get_json()["checked"] == 2


def test_private_wishlist_still_checks_the_file(tmp_path):
    def private(profile):
        raise steam.ProfileError("the wishlist is empty or private")

    app = create_app(str(tmp_path / "p.db"), fetch_prices=fake_prices, fetch_games=fake_games,
                     watchlist=lambda: {1174180: None}, profile="vini", fetch_wishlist=private)
    out = app.test_client().post("/check").get_json()
    assert out["checked"] == 1
    assert out["warnings"] == ["wishlist skipped: the wishlist is empty or private"]


def test_page_lists_the_games_with_their_history(tmp_path):
    c = client(tmp_path)
    prices[1174180] = 29990
    c.post("/check")
    prices[1174180] = 7497
    c.post("/check")
    html = c.get("/").get_data(as_text=True)
    assert "Game 1174180" in html
    assert "R$ 74,97" in html and "-75%" in html
    assert "<polyline" in html


def test_page_before_the_first_check(tmp_path):
    assert "Nothing yet" in client(tmp_path).get("/").get_data(as_text=True)


def test_money_formats():
    from price_watch.api import money
    assert money(7497, "BRL") == "R$ 74,97"
    assert money(123456, "BRL") == "R$ 1.234,56"
    assert money(1999, "USD") == "19.99 USD"
