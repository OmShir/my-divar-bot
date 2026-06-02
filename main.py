from analyzer import *
from notifier import *

ads = [
    {
        "title": "PS5 Slim",
        "price": 19000000,
        "url": "..."
    },
    {
        "title": "PS5 Slim",
        "price": 24000000,
        "url": "..."
    },
    {
        "title": "PS5 Slim",
        "price": 25000000,
        "url": "..."
    }
]

prices = [
    x["price"]
    for x in ads
]

market = market_price(
    prices
)

for ad in ads:

    s = score(
        ad["price"],
        market
    )

    if s > 15:

        send(
            f"""
🔥 Opportunity

{ad['title']}

Price:
{ad['price']:,}

Market:
{market:,.0f}

Discount:
{s:.1f}%

{ad['url']}
"""
        )
