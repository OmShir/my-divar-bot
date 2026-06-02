import re


def extract_price(text):

    if not text:
        return 0

    nums = re.findall(r"\d+", str(text))

    if not nums:
        return 0

    return int("".join(nums))


def parse_ads(data):

    ads = []

    try:

        widgets = data.get("web_widgets", [])

        for w in widgets:

            if w.get("@type") != "POST_ROW":
                continue

            d = w.get("data", {})

            ads.append({
                "title": d.get("title", ""),
                "price": extract_price(
                    d.get("middle_description")
                ),
                "url": "https://divar.ir/v/" + d.get(
                    "action", {}
                ).get(
                    "payload", {}
                ).get(
                    "web_url", ""
                )
            })

    except Exception as e:
        print("PARSE ERROR:", e)

    return ads
