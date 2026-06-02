import numpy as np


def detect_model(title):

    t = title.lower()

    if "pro" in t:
        return "PS5 Pro"

    if "slim" in t:
        return "PS5 Slim"

    return "PS5"


def market_price(prices):

    return np.median(prices)


def score(price, market):

    if market == 0:
        return 0

    return ((market - price) / market) * 100


def is_good_deal(score_value, min_score):

    return score_value >= min_score
