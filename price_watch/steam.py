"""Reads game prices from the Steam store's public appdetails endpoint (no key needed)."""

import os
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# overridable so CI can point it at a fake store instead of the real one
STORE_URL = os.getenv("STEAM_STORE_URL", "https://store.steampowered.com")
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


def fetch_prices(appids: list[int], session: requests.Session | None = None) -> list[Price]:
    session = session or make_session()
    # with filters=price_overview the endpoint takes many ids in one call
    res = session.get(f"{STORE_URL}/api/appdetails", headers=HEADERS, timeout=20, params={
        "appids": ",".join(map(str, appids)), "cc": COUNTRY, "filters": "price_overview"})
    res.raise_for_status()
    return parse_prices(res.json())


def fetch_game(appid: int, session: requests.Session | None = None) -> Game | None:
    """Name and banner of one game. The basic filter only works one id at a time."""
    session = session or make_session()
    res = session.get(f"{STORE_URL}/api/appdetails", headers=HEADERS, timeout=20, params={
        "appids": appid, "cc": COUNTRY, "filters": "basic"})
    res.raise_for_status()
    entry = res.json().get(str(appid), {})
    data = entry.get("data") if entry.get("success") else None
    if not isinstance(data, dict):
        return None
    return Game(appid=appid, name=data["name"], image=data.get("header_image", ""))


def store_page(appid: int) -> str:
    return f"https://store.steampowered.com/app/{appid}/"
