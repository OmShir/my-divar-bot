import re


def detect_model(title):

    t = title.lower()

    if "pro" in t:
        return "PS5 Pro"

    if "slim" in t:
        return "PS5 Slim"

    return "PS5"


def extract_storage(title):

    t = title.lower()

    if "1tb" in t:
        return "1TB"

    if "825" in t:
        return "825GB"

    return "Unknown"


def extract_price(text):

    digits = re.findall(
        r"\d+",
        text
    )

    if not digits:
        return None

    return int(
        "".join(digits)
    )
