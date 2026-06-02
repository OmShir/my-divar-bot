import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}


URL = "https://api.divar.ir/v8/web-search/tehran/game-console"


def fetch_raw():

    try:

        r = requests.get(
            URL,
            headers=HEADERS,
            timeout=15
        )

        print("STATUS:", r.status_code)

        data = r.json()

        print("KEYS:", data.keys())

        return data

    except Exception as e:

        print("ERROR:", e)

        return None
