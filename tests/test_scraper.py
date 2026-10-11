from pathlib import Path

from price_watch import scraper

FIXTURES = Path(__file__).parent / "fixtures"
PAGE_1 = "https://books.toscrape.com/catalogue/page-1.html"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_list_reads_title_price_and_stock():
    books, nxt = scraper.parse_list(fixture("page-1.html"), PAGE_1)
    assert [b.title for b in books] == ["A Light in the Attic", "Tipping the Velvet"]
    assert books[0].url == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"
    assert books[0].price == 51.77 and books[0].in_stock
    assert books[1].price == 53.74 and not books[1].in_stock
    assert nxt == "https://books.toscrape.com/catalogue/page-2.html"


def test_last_page_has_no_next():
    _, nxt = scraper.parse_list(fixture("page-2.html"), PAGE_1)
    assert nxt is None


class FakeResponse:
    def __init__(self, url, text):
        self.url, self.text, self.encoding = url, text, None

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **_):
        self.calls.append(url)
        return FakeResponse(url, fixture(url.rsplit("/", 1)[1]))


def test_scrape_follows_next_until_max_pages():
    session = FakeSession()
    books = scraper.scrape(PAGE_1, max_pages=5, delay=0, session=session)
    assert len(books) == 3
    assert len(session.calls) == 2

    session = FakeSession()
    assert len(scraper.scrape(PAGE_1, max_pages=1, delay=0, session=session)) == 2
