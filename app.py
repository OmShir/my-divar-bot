from collector import collect_raw
from parser import parse_ads
from analyzer import *
from notifier import send
from storage import load_seen, save_seen
from config import MIN_SCORE


def run():

    state = collect_raw()
    ads = parse_ads(state)

    if not ads:
        return

    seen = load_seen()

    prices = [
        a["price"] for a in ads
        if a["price"] > 0
    ]

    if len(prices) < 5:
        return

    market = market_price(prices)

    for ad in ads:

        if ad["url"] in seen:
            continue

        s = score(ad["price"], market)

        if is_good_deal(s, MIN_SCORE):

            msg = f"""
🔥 PS5 Opportunity

{ad['title']}

Price: {ad['price']:,}
Market: {int(market):,}
Discount: {s:.1f}%

{ad['url']}
"""

            send(msg)

            seen.add(ad["url"])

    save_seen(seen)


if __name__ == "__main__":
    run()
