import re
import json
import httpx

ROOMS_MAP = {
    "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4",
    "FIVE": "5", "SIX": "6", "SEVEN_OR_MORE": "7+",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "pl-PL,pl;q=0.9",
}


def _parse_next_data(html: str) -> dict:
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        raise ValueError("__NEXT_DATA__ not found in page")
    return json.loads(m.group(1))


def fetch_search(url: str) -> list[dict]:
    response = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    response.raise_for_status()
    data = _parse_next_data(response.text)
    items = data["props"]["pageProps"]["data"]["searchAds"]["items"]
    return [_parse_item(item) for item in items]


def _parse_item(raw: dict) -> dict:
    rent = (raw.get("rentPrice") or {}).get("value", 0) or 0
    total = (raw.get("totalPrice") or {}).get("value", 0) or 0
    price = rent if rent > 0 else total

    locations = raw["location"]["reverseGeocoding"]["locations"]
    district = next(
        (loc["name"] for loc in locations if loc["locationLevel"] == "district"),
        None,
    )

    return {
        "id": str(raw["id"]),
        "slug": raw["slug"],
        "title": raw["title"],
        "price": price,
        "area": raw.get("areaInSquareMeters"),
        "rooms": ROOMS_MAP.get(raw.get("roomsNumber", ""), raw.get("roomsNumber", "")),
        "city": raw["location"]["address"]["city"]["name"],
        "district": district,
        "url": f"https://www.otodom.pl/pl/oferta/{raw['slug']}",
    }


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _get_characteristic(characteristics: list[dict], key: str) -> str | None:
    for item in characteristics:
        if item.get("key") == key:
            value = item.get("value", "")
            if value and value != "0":
                return item.get("localizedValue")
            return None
    return None


def fetch_detail(slug: str) -> dict:
    url = f"https://www.otodom.pl/pl/oferta/{slug}"
    response = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    response.raise_for_status()
    data = _parse_next_data(response.text)
    ad = data["props"]["pageProps"]["ad"]
    description = _strip_html(ad.get("description", ""))
    photos = [img["large"] for img in ad.get("images", []) if img.get("large")]
    characteristics = ad.get("characteristics", []) or []
    agency = ad.get("agency") or {}
    return {
        "description": description,
        "photos": photos,
        "rent": _get_characteristic(characteristics, "rent"),
        "deposit": _get_characteristic(characteristics, "deposit"),
        "advertiser_type": ad.get("advertiserType", "private"),
        "agency_name": agency.get("name"),
    }
