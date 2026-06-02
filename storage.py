import json
import os

FILE = "seen.json"


def load_seen():

    if not os.path.exists(FILE):
        return set()

    try:
        with open(FILE, "r") as f:
            return set(json.load(f))
    except:
        return set()


def save_seen(seen):

    with open(FILE, "w") as f:
        json.dump(list(seen), f)
