"""Talks to Steam's public endpoints (no key needed): prices, names and wishlists."""

import json
import os
import re
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# overridable so CI can point it at a fake store instead of the real one
STORE_URL = os.getenv("STEAM_STORE_URL", "https://store.steampowered.com")
API_URL = os.getenv("STEAM_API_URL", "https://api.steampowered.com")
COMMUNITY_URL = os.getenv("STEAM_COMMUNITY_URL", "https://steamcommunity.com")
IMAGES_URL = "https://shared.akamai.steamstatic.com/store_item_assets/"
# ids per call: keeps the urls short, a big wishlist goes in a few calls
BATCH = 100
COUNTRY = os.getenv("STEAM_COUNTRY", "br")
HEADERS = {"User-Agent": "price-watch-n8n (study project)"}


@dataclass
class Price:
    appid: int
    currency: str
    initial: int  # in cents, like the API sends it
    final: int
    discount: int


@dataclass
class Game:
    appid: int
    name: str
    image: str


class ProfileError(Exception):
    """A Steam profile that can't be found, or whose wishlist isn't public."""


def make_session() -> requests.Session:
    # n8n calls /check once a day, so a single 503 or dropped connection would
    # cost a whole day of history. Retry a few times with backoff instead.
    retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def parse_prices(payload: dict) -> list[Price]:
    """Turns an appdetails?filters=price_overview answer into prices.

    Games that don't exist come back with success false, and free ones (or ones
    not sold in the country) have no price_overview at all: both are skipped.
    """
    prices = []
    for appid, entry in payload.items():
        data = entry.get("data") if entry.get("success") else None
        # free games answer with an empty list instead of an object
        overview = data.get("price_overview") if isinstance(data, dict) else None
        if not overview:
            continue
        prices.append(Price(
            appid=int(appid),
            currency=overview["currency"],
            initial=int(overview["initial"]),
            final=int(overview["final"]),
            discount=int(overview["discount_percent"]),
        ))
    return prices


def batches(appids: list[int]):
    for start in range(0, len(appids), BATCH):
        yield appids[start:start + BATCH]


def fetch_prices(appids: list[int], session: requests.Session | None = None) -> list[Price]:
    session = session or make_session()
    prices = []
    # with filters=price_overview the endpoint takes many ids in one call
    for chunk in batches(appids):
        res = session.get(f"{STORE_URL}/api/appdetails", headers=HEADERS, timeout=20, params={
            "appids": ",".join(map(str, chunk)), "cc": COUNTRY, "filters": "price_overview"})
        res.raise_for_status()
        prices.extend(parse_prices(res.json()))
    return prices


def parse_items(payload: dict) -> dict[int, Game]:
    """Name and banner of each game in an IStoreBrowseService/GetItems answer."""
    games = {}
    for item in payload.get("response", {}).get("store_items", []):
        # an id that doesn't exist comes back with success 15 and an empty name
        if item.get("success") != 1 or not item.get("name"):
            continue
        assets = item.get("assets") or {}
        image = ""
        if assets.get("asset_url_format") and assets.get("header"):
            image = IMAGES_URL + assets["asset_url_format"].replace("${FILENAME}", assets["header"])
        games[int(item["appid"])] = Game(appid=int(item["appid"]), name=item["name"], image=image)
    return games


def fetch_games(appids: list[int], session: requests.Session | None = None) -> dict[int, Game]:
    """Names and banners, many games per call (appdetails only does one at a time for these)."""
    session = session or make_session()
    games = {}
    for chunk in batches(appids):
        query = {"ids": [{"appid": a} for a in chunk],
                 "context": {"language": "english", "country_code": COUNTRY.upper()},
                 "data_request": {"include_assets": True}}
        res = session.get(f"{API_URL}/IStoreBrowseService/GetItems/v1/", headers=HEADERS, timeout=20,
                          params={"input_json": json.dumps(query)})
        res.raise_for_status()
        games.update(parse_items(res.json()))
    return games


def steamid_of(profile: str, session: requests.Session | None = None) -> str:
    """The 17-digit id behind whatever the user pasted: the id, a profile url or the custom name."""
    profile = profile.strip().rstrip("/")
    if re.fullmatch(r"\d{17}", profile):
        return profile
    if match := re.search(r"/profiles/(\d{17})", profile):
        return match.group(1)
    match = re.search(r"/id/([^/?#]+)", profile)
    name = match.group(1) if match else profile
    if not re.fullmatch(r"[\w-]+", name):
        raise ProfileError(f"{profile!r} doesn't look like a Steam profile")
    # the profile page has an xml version with the id in it, no key needed
    session = session or make_session()
    res = session.get(f"{COMMUNITY_URL}/id/{name}/", params={"xml": 1}, headers=HEADERS, timeout=20)
    res.raise_for_status()
    found = re.search(r"<steamID64>(\d{17})</steamID64>", res.text)
    if not found:
        raise ProfileError(f"no Steam profile called {name!r}")
    return found.group(1)


def parse_wishlist(payload: dict) -> list[int]:
    items = payload.get("response", {}).get("items", [])
    return [int(item["appid"]) for item in sorted(items, key=lambda i: i.get("priority", 0))]


def fetch_wishlist(profile: str, session: requests.Session | None = None) -> list[int]:
    session = session or make_session()
    steamid = steamid_of(profile, session)
    res = session.get(f"{API_URL}/IWishlistService/GetWishlist/v1/", params={"steamid": steamid},
                      headers=HEADERS, timeout=20)
    res.raise_for_status()
    appids = parse_wishlist(res.json())
    if not appids:
        # a private wishlist answers just like an empty one: {"response": {}}
        raise ProfileError("the wishlist is empty or private (Steam > Privacy settings > Game details: Public)")
    return appids


def store_page(appid: int) -> str:
    return f"https://store.steampowered.com/app/{appid}/"
