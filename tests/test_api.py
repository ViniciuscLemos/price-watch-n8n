from price_watch.api import create_app, load_watchlist
from price_watch.steam import Game, Price

prices = {1174180: 29990}
calls = {"game": 0}


def fake_prices(appids):
    return [Price(a, "BRL", 29990, prices.get(a, 29990), 0 if prices.get(a, 29990) == 29990 else 75)
            for a in appids]


def fake_game(appid):
    calls["game"] += 1
    return Game(appid, f"Game {appid}", "")


def client(tmp_path):
    return create_app(str(tmp_path / "test.db"), fetch_prices=fake_prices, fetch_game=fake_game,
                      watchlist=lambda: [1174180]).test_client()


def test_check_returns_deals_between_runs(tmp_path):
    c = client(tmp_path)
    prices[1174180] = 29990
    calls["game"] = 0
    assert c.post("/check", json={}).get_json() == {"checked": 1, "deals": []}

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
    appids = load_watchlist()
    assert len(appids) == len(set(appids)) >= 10
