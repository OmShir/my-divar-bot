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

        if r.status_code != 200:
            return None

        data = r.json()

        print("RAW KEYS:", data.keys())

        return data

    except Exception as e:

        print("FETCH ERROR:", e)

        return None
