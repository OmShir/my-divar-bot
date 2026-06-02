import numpy as np


def market_price(prices):

    if not prices:
        return 0

    return np.median(prices)


def score(price, market):

    if market == 0:
        return 0

    return ((market - price) / market) * 100


def is_good(score_value, min_score):

    return score_value >= min_score
