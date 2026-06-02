def parse_ads(data):

    ads = []

    try:

        widgets = data.get("widget_list", [])

        for w in widgets:

            widget_type = w.get("@type")

            # مهم‌ترین تغییر: اینجا SEARCH_RESULT_PAGE است
            if widget_type != "SEARCH_RESULT_PAGE":
                continue

            items = w.get("data", {}).get("items", [])

            for item in items:

                try:

                    action = item.get("action", {})

                    payload = action.get("payload", {})

                    ads.append({
                        "title": item.get("title", ""),
                        "price": item.get("middle_description", ""),
                        "url": "https://divar.ir/v/" + payload.get("web_url", "")
                    })

                except:
                    continue

    except Exception as e:
        print("PARSE ERROR:", e)

    return ads
