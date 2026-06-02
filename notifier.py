import requests
import config


def send(text):

    url = f"https://api.telegram.org/bot{config.BOT_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": config.CHAT_ID,
            "text": text
        }
    )
