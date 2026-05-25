import httpx

_API = "https://api.telegram.org/bot{token}/{method}"


def _build_caption(listing: dict) -> str:
    lines = [f"\U0001f3e0 {listing['title']}"]
    lines.append(f"\U0001f4b0 Cena: {listing['price']} zł/mies")

    if listing.get("rent"):
        lines.append(f"\U0001f9fe Czynsz: {listing['rent']}")
    if listing.get("deposit"):
        lines.append(f"\U0001f510 Kaucja: {listing['deposit']}")

    lines.append(
        f"\U0001f4d0 {listing['area']} m²"
        f" • \U0001f6cf {listing['rooms']} pok."
    )

    district = listing.get("district")
    location = f"{listing['city']}, {district}" if district else listing['city']
    lines.append(f"\U0001f4cd {location}")

    advertiser = listing.get("advertiser_type")
    agency_name = listing.get("agency_name")
    if advertiser == "business":
        if agency_name:
            lines.append(f"\U0001f3e2 Rieltor: {agency_name}")
        else:
            lines.append("\U0001f3e2 Rieltor")
    else:
        lines.append("\U0001f464 Bezpośrednio")

    lines.append(f"\U0001f517 {listing['url']}")

    return "\n".join(lines)[:1024]


def _post(token: str, method: str, payload: dict) -> None:
    url = _API.format(token=token, method=method)
    response = httpx.post(url, json=payload, timeout=30)
    response.raise_for_status()


def send_telegram(token: str, chat_id: str, listing: dict, photos: list[str]) -> None:
    caption = _build_caption(listing)
    photos = photos[:10]

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
