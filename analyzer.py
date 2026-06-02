import statistics


def market_price(prices):

    return statistics.median(
        prices
    )


def score(
        ad_price,
        market):

    return (
        market-ad_price
    ) / market * 100
