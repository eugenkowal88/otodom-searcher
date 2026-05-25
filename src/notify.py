import httpx

_API = "https://api.telegram.org/bot{token}/{method}"


def _build_caption(listing: dict) -> str:
    district = listing.get("district")
    location = f"{listing['city']}, {district}" if district else listing["city"]
    caption = (
        f"\U0001f3e0 {listing['title']}\n"
        f"\U0001f4b0 {listing['price']} zł/mies"
        f" • \U0001f4d0 {listing['area']} m²"
        f" • \U0001f6cf {listing['rooms']} pok.\n"
        f"\U0001f4cd {location}\n"
        f"\U0001f517 {listing['url']}"
    )
    return caption[:1024]


def _post(token: str, method: str, payload: dict) -> None:
    url = _API.format(token=token, method=method)
    response = httpx.post(url, json=payload, timeout=30)
    response.raise_for_status()


def send_telegram(token: str, chat_id: str, listing: dict, photos: list[str]) -> None:
    caption = _build_caption(listing)
    photos = photos[:3]

    if not photos:
        _post(token, "sendMessage", {"chat_id": chat_id, "text": caption})
    elif len(photos) == 1:
        _post(token, "sendPhoto", {
            "chat_id": chat_id,
            "photo": photos[0],
            "caption": caption,
        })
    else:
        media = [{"type": "photo", "media": url} for url in photos]
        media[0]["caption"] = caption
        _post(token, "sendMediaGroup", {"chat_id": chat_id, "media": media})
