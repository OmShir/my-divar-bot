def parse_ads(state):

    ads = []

    try:
        widgets = state.get("widgetList", [])

        for w in widgets:

            data = w.get("data")

            if not data:
                continue

            for item in data:

                try:
                    ads.append({
                        "title": item.get("title", ""),
                        "price": item.get("price", 0),
                        "url": "https://divar.ir/v/" + item.get("token", "")
                    })

                except:
                    continue

    except:
        pass

    return ads[:30]
