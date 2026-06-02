import requests
from bs4 import BeautifulSoup
import json
import re
from config import URL


HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def fetch_html():
    r = requests.get(URL, headers=HEADERS, timeout=15)
    return r.text


def extract_state(html):
    match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
        html
    )

    if not match:
        return None

    try:
        return json.loads(match.group(1))
    except:
        return None


def collect_raw():
    html = fetch_html()
    state = extract_state(html)

    if not state:
        return []

    return state
