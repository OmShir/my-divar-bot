from collector import fetch_raw
from parser import parse_ads
from analyzer import *
from notifier import send
from storage import load_seen, save_seen
from config import MIN_SCORE


def run():

    print("START")

    data = fetch_raw()

    if not data:
        print("No data from API")
        return

    ads = parse_ads(data)

    print("ADS:", len(ads))

    if len(ads) < 5:
        print("Not enough ads")
        return

    seen = load_seen()

    prices = [
        a["price"]
        for a in ads
        if a["price"] > 0
    ]

    market = market_price(prices)

    print("Market:", market)

    for ad in ads:

        if ad["url"] in seen:
            continue

        if ad["price"] == 0:
            continue

        s = score(ad["price"], market)

        if is_good(s, MIN_SCORE):

            msg = f"""
🔥 PS5 DEAL

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
