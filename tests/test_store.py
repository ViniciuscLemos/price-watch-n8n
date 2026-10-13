from price_watch import store
from price_watch.scraper import Book


def book(price=10.0, in_stock=True, url="u1"):
    return Book(url=url, title="Some Book", price=price, in_stock=in_stock)


def test_first_run_reports_nothing():
    conn = store.connect(":memory:")
    assert store.record(conn, [book(), book(url="u2")]) == []


def test_price_drop_and_back_in_stock():
    conn = store.connect(":memory:")
    store.record(conn, [book(20.0, in_stock=False)])
    changes = store.record(conn, [book(15.5, in_stock=True)])
    assert {c["kind"] for c in changes} == {"price_drop", "back_in_stock"}
    drop = next(c for c in changes if c["kind"] == "price_drop")
    assert drop["old_price"] == 20.0 and drop["price"] == 15.5


def test_price_going_up_is_saved_but_not_reported():
    conn = store.connect(":memory:")
    store.record(conn, [book(10.0)])
    assert store.record(conn, [book(12.0)]) == []
    assert [h["price"] for h in store.history(conn, "u1")] == [10.0, 12.0]
    # and dropping back from 12 counts as a drop
    assert store.record(conn, [book(11.0)])[0]["old_price"] == 12.0


def test_same_price_does_not_grow_history():
    conn = store.connect(":memory:")
    for _ in range(3):
        store.record(conn, [book(10.0)])
    assert len(store.history(conn, "u1")) == 1


def test_demo_changes_show_up_on_next_check():
    from price_watch.demo import make_changes
    conn = store.connect(":memory:")
    books = [book(10.0, url=f"u{i}") for i in range(4)]
    store.record(conn, books)
    make_changes(conn, 2, seed=1)
    kinds = sorted(c["kind"] for c in store.record(conn, books))
    assert kinds == ["back_in_stock", "price_drop"]


def test_demo_old_price_has_two_decimals():
    from price_watch.demo import make_changes
    conn = store.connect(":memory:")
    books = [book(31.77, url="u0")]
    store.record(conn, books)
    make_changes(conn, 1, seed=1)
    (change,) = store.record(conn, books)
    assert change["old_price"] == 36.77
