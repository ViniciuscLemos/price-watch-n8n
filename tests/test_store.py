from price_watch import store
from price_watch.steam import Game, Price

GAMES = {1: Game(1, "Terraria", "https://img/1.jpg"), 2: Game(2, "Hades II", "https://img/2.jpg")}


def price(appid, final, initial=None, discount=0):
    return Price(appid=appid, currency="BRL", initial=initial or final, final=final, discount=discount)


def test_first_sight_only_reports_games_already_on_sale():
    conn = store.connect(":memory:")
    deals = store.record(conn, [price(1, 1649, 3299, 50), price(2, 8899)], GAMES)
    assert [d["name"] for d in deals] == ["Terraria"]
    assert deals[0]["old_price"] == 3299
    assert deals[0]["lowest"] is False


def test_a_sale_that_goes_on_is_not_news_again():
    conn = store.connect(":memory:")
    store.record(conn, [price(1, 1649, 3299, 50)], GAMES)
    assert store.record(conn, [price(1, 1649, 3299, 50)], {}) == []


def test_cheaper_than_last_time_is_a_deal_and_a_new_low():
    conn = store.connect(":memory:")
    store.record(conn, [price(2, 8899)], GAMES)
    (deal,) = store.record(conn, [price(2, 6229, 8899, 30)], {})
    assert (deal["price"], deal["old_price"], deal["discount"], deal["lowest"]) == (6229, 8899, 30, True)
    assert deal["url"] == "https://store.steampowered.com/app/2/"


def test_dropping_back_to_an_old_low_is_not_a_new_low():
    conn = store.connect(":memory:")
    store.record(conn, [price(2, 6229, 8899, 30)], GAMES)
    store.record(conn, [price(2, 8899)], {})
    (deal,) = store.record(conn, [price(2, 6229, 8899, 30)], {})
    assert deal["lowest"] is False


def test_biggest_discount_first():
    conn = store.connect(":memory:")
    deals = store.record(conn, [price(2, 6229, 8899, 30), price(1, 1649, 3299, 50)], GAMES)
    assert [d["discount"] for d in deals] == [50, 30]


def test_game_without_a_name_is_skipped_until_it_has_one():
    conn = store.connect(":memory:")
    assert store.record(conn, [price(3, 1000)], GAMES) == []
    assert not store.known(conn, 3)


def test_history_only_grows_when_the_price_changes():
    conn = store.connect(":memory:")
    for final in (8899, 8899, 6229, 6229, 8899):
        store.record(conn, [price(2, final)], GAMES)
    assert [h["price"] for h in store.history(conn, 2)] == [8899, 6229, 8899]


def test_demo_makes_the_next_check_find_deals():
    from price_watch.demo import make_changes
    conn = store.connect(":memory:")
    store.record(conn, [price(1, 3299), price(2, 8899)], GAMES)
    make_changes(conn, 2, seed=1)
    deals = store.record(conn, [price(1, 3299), price(2, 8899)], {})
    assert sorted((d["name"], d["old_price"], d["lowest"]) for d in deals) == [
        ("Hades II", 10678, True), ("Terraria", 3958, True)]


def test_under_target_on_first_sight_is_a_deal_even_without_a_sale():
    conn = store.connect(":memory:")
    (deal,) = store.record(conn, [price(2, 8899)], GAMES, targets={2: 9000})
    assert (deal["below_target"], deal["target"], deal["discount"]) == (True, 9000, 0)


def test_over_target_without_a_sale_is_quiet():
    conn = store.connect(":memory:")
    assert store.record(conn, [price(2, 8899)], GAMES, targets={2: 5000}) == []


def test_a_drop_says_whether_it_is_under_target():
    conn = store.connect(":memory:")
    store.record(conn, [price(2, 8899)], GAMES, targets={2: 5000})
    (deal,) = store.record(conn, [price(2, 6229, 8899, 30)], {}, targets={2: 5000})
    assert deal["below_target"] is False
    (deal,) = store.record(conn, [price(2, 4449, 8899, 50)], {}, targets={2: 5000})
    assert deal["below_target"] is True
