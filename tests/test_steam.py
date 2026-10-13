import pytest
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


def test_names_and_banners_come_in_one_call():
    session = FakeSession(load("items.json"))
    games = steam.fetch_games([1245620, 1174180, 999999999], session=session)
    assert len(session.calls) == 1
    assert games[1245620].name == "ELDEN RING"
    assert games[1174180].image.startswith("https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1174180/header.jpg")
    assert 999999999 not in games  # success 15, no name


def test_big_lists_go_in_batches():
    session = FakeSession({})
    steam.fetch_prices(list(range(1, 251)), session=session)
    assert [len(params["appids"].split(",")) for _, params in session.calls] == [100, 100, 50]


class TextSession(FakeSession):
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs.get("params")))
        res = FakeResponse(self.payload)
        res.text = self.payload
        return res


def test_steamid_from_what_people_paste():
    assert steam.steamid_of("76561198000000001") == "76561198000000001"
    assert steam.steamid_of("https://steamcommunity.com/profiles/76561198000000001/") == "76561198000000001"
    xml = "<profile><steamID64>76561198000000002</steamID64></profile>"
    for pasted in ("vini", "https://steamcommunity.com/id/vini/", "steamcommunity.com/id/vini"):
        session = TextSession(xml)
        assert steam.steamid_of(pasted, session=session) == "76561198000000002"
        assert session.calls[0][0].endswith("/id/vini/")


def test_unknown_profile_name():
    with pytest.raises(steam.ProfileError):
        steam.steamid_of("nobody", session=TextSession("<response><error>The specified profile could not be found.</error></response>"))
    with pytest.raises(steam.ProfileError):
        steam.steamid_of("not a profile!")


def test_wishlist_in_priority_order():
    assert steam.parse_wishlist(load("wishlist.json")) == [1030300, 1174180, 2246340]


def test_private_wishlist_says_so():
    with pytest.raises(steam.ProfileError, match="private"):
        steam.fetch_wishlist("76561198000000001", session=FakeSession({"response": {}}))
