import requests
from bs4 import BeautifulSoup
import re
import time


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122 Safari/537.36"
    )
}


URL = "https://divar.ir/s/tehran/game-consoles"



def fetch_page():

    r = requests.get(
        URL,
        headers=HEADERS,
        timeout=15
    )

    return r.text
