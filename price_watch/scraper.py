"""Scrapes the book list pages of books.toscrape.com (price + stock)."""

import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://books.toscrape.com/"
HEADERS = {"User-Agent": "price-watch-n8n (study project)"}


@dataclass
class Book:
    url: str
    title: str
    price: float
    in_stock: bool


def parse_price(text: str) -> float:
    # The site sends "£51.77", sometimes with a stray "Â" when the encoding
    # gets guessed wrong, so I just keep the number.
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        raise ValueError(f"no price in {text!r}")
    return float(match.group())


def parse_list(html: str, page_url: str) -> tuple[list[Book], str | None]:
    """Returns the books on one list page and the url of the next page (or None)."""
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for pod in soup.select("article.product_pod"):
        link = pod.select_one("h3 a")
        price = pod.select_one("p.price_color")
        stock = pod.select_one("p.availability")
        if not link or not price:
            continue
        books.append(Book(
            url=urljoin(page_url, link["href"]),
            # the visible text is cut with "...", the title attribute isn't
            title=link.get("title") or link.get_text(strip=True),
            price=parse_price(price.get_text()),
            in_stock=bool(stock) and "in stock" in stock.get_text().lower(),
        ))
    nxt = soup.select_one("li.next a")
    return books, urljoin(page_url, nxt["href"]) if nxt else None


def make_session() -> requests.Session:
    # n8n calls /check once a day, so a single 503 or dropped connection would
    # cost a whole day of history. Retry a few times with backoff instead.
    retry = Retry(total=3, backoff_factor=1, status_forcelist=(429, 500, 502, 503, 504),
                  allowed_methods=("GET",))
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def scrape(start_url: str = BASE_URL, max_pages: int = 3, delay: float = 0.5,
           session: requests.Session | None = None) -> list[Book]:
    session = session or make_session()
    books: list[Book] = []
    url: str | None = start_url
    for page in range(max_pages):
        if not url:
            break
        if page:
            time.sleep(delay)  # be nice to the site, it's a free practice server
        res = session.get(url, headers=HEADERS, timeout=15)
        res.raise_for_status()
        res.encoding = "utf-8"
        found, url = parse_list(res.text, res.url)
        books.extend(found)
    return books
