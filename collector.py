import requests
from config import LIMIT

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}


URL = "https://api.divar.ir/v8/web-search/"


def fetch_raw():

    payload = {
        "json_schema": {
            "category": {
                "value": "game-console"
            },
            "query": "PS5"
        },
        "size": LIMIT
    }

    r = requests.post(
        URL,
        json=payload,
        headers=HEADERS,
        timeout=15
    )

    if r.status_code != 200:
        print("HTTP ERROR:", r.status_code)
        return None

    return r.json()
