import json
from pathlib import Path

from price_watch import steam

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text("utf-8"))


def test_parses_prices_in_cents():
    prices = {p.appid: p for p in steam.parse_prices(load("prices.json"))}
    rdr2 = prices[1174180]
    assert (rdr2.currency, rdr2.initial, rdr2.final, rdr2.discount) == ("BRL", 29990, 7497, 75)
    assert prices[1245620].discount == 0


def test_skips_free_and_missing_games():
    appids = {p.appid for p in steam.parse_prices(load("prices.json"))}
    assert 570 not in appids  # Dota 2 is free: its data is an empty list
    assert 999999999 not in appids  # no such game: success is false
    assert len(appids) == 15


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs["params"]))
        return FakeResponse(self.payload)


def test_fetch_prices_asks_for_all_ids_in_one_call():
    session = FakeSession(load("prices.json"))
    steam.fetch_prices([1245620, 1174180], session=session)
    (url, params), = session.calls
    assert url.endswith("/api/appdetails")
    assert params == {"appids": "1245620,1174180", "cc": "br", "filters": "price_overview"}


def test_fetch_game_reads_name_and_banner():
    game = steam.fetch_game(1245620, session=FakeSession(load("basic-1245620.json")))
    assert game.name == "ELDEN RING"
    assert "header.jpg" in game.image


def test_fetch_game_that_does_not_exist():
    assert steam.fetch_game(999999999, session=FakeSession({"999999999": {"success": False}})) is None
