import json
from unittest.mock import patch, MagicMock

from src.otodom import fetch_search, fetch_detail


SEARCH_NEXT_DATA = {
    "props": {
        "pageProps": {
            "data": {
                "searchAds": {
                    "items": [
                        {
                            "id": 12345,
                            "slug": "mieszkanie-mokotow-ID12345",
                            "title": "Mieszkanie 3-pok. z balkonem",
                            "totalPrice": {"value": 3500, "currency": "PLN"},
                            "rentPrice": {"value": 3200, "currency": "PLN"},
                            "areaInSquareMeters": 65,
                            "roomsNumber": "THREE",
                            "location": {
                                "address": {"city": {"name": "Warszawa"}},
                                "reverseGeocoding": {
                                    "locations": [
                                        {"name": "mazowieckie", "locationLevel": "voivodeship"},
                                        {"name": "Warszawa", "locationLevel": "city_or_village"},
                                        {"name": "Mokotów", "locationLevel": "district"},
                                    ]
                                },
                            },
                            "images": [
                                {"large": "https://img.example.com/photo1.jpg"},
                                {"large": "https://img.example.com/photo2.jpg"},
                            ],
                        }
                    ]
                }
            }
        }
    }
}

SEARCH_HTML = (
    '<!DOCTYPE html><html><body>'
    f'<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">'
    f'{json.dumps(SEARCH_NEXT_DATA)}'
    '</script></body></html>'
)


def _mock_get(html):
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()
    return response


def test_fetch_search_parses_listing():
    with patch("httpx.get", return_value=_mock_get(SEARCH_HTML)):
        items = fetch_search("https://www.otodom.pl/pl/wyniki/wynajem/...")

    assert len(items) == 1
    item = items[0]
    assert item["id"] == "12345"
    assert item["slug"] == "mieszkanie-mokotow-ID12345"
    assert item["title"] == "Mieszkanie 3-pok. z balkonem"
    assert item["price"] == 3200          # rentPrice wins over totalPrice
    assert item["area"] == 65
    assert item["rooms"] == "3"           # "THREE" mapped to "3"
    assert item["city"] == "Warszawa"
    assert item["district"] == "Mokotów"
    assert item["url"] == "https://www.otodom.pl/pl/oferta/mieszkanie-mokotow-ID12345"


def test_fetch_search_uses_total_price_when_rent_is_zero():
    data = json.loads(json.dumps(SEARCH_NEXT_DATA))
    data["props"]["pageProps"]["data"]["searchAds"]["items"][0]["rentPrice"]["value"] = 0
    html = (
        '<html><body>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        '</body></html>'
    )
    with patch("httpx.get", return_value=_mock_get(html)):
        items = fetch_search("https://www.otodom.pl/...")
    assert items[0]["price"] == 3500


def test_fetch_search_district_none_when_missing():
    data = json.loads(json.dumps(SEARCH_NEXT_DATA))
    data["props"]["pageProps"]["data"]["searchAds"]["items"][0][
        "location"
    ]["reverseGeocoding"]["locations"] = [
        {"name": "mazowieckie", "locationLevel": "voivodeship"}
    ]
    html = (
        '<html><body>'
        f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
        '</body></html>'
    )
    with patch("httpx.get", return_value=_mock_get(html)):
        items = fetch_search("https://www.otodom.pl/...")
    assert items[0]["district"] is None


DETAIL_NEXT_DATA = {
    "props": {
        "pageProps": {
            "ad": {
                "description": "<p>Piękne mieszkanie z <strong>balkonem</strong>.<br>Świeży remont.</p>",
                "images": [
                    {"large": "https://img.example.com/d1.jpg"},
                    {"large": "https://img.example.com/d2.jpg"},
                    {"large": "https://img.example.com/d3.jpg"},
                    {"large": "https://img.example.com/d4.jpg"},
                    {"large": "https://img.example.com/d5.jpg"},
                ],
            }
        }
    }
}

DETAIL_HTML = (
    '<!DOCTYPE html><html><body>'
    f'<script id="__NEXT_DATA__" type="application/json" crossorigin="anonymous">'
    f'{json.dumps(DETAIL_NEXT_DATA)}'
    '</script></body></html>'
)


def test_fetch_detail_strips_html_from_description():
    with patch("httpx.get", return_value=_mock_get(DETAIL_HTML)):
        detail = fetch_detail("mieszkanie-mokotow-ID12345")
    assert "<p>" not in detail["description"]
    assert "balkonem" in detail["description"]
    assert "Świeży remont" in detail["description"]


def test_fetch_detail_returns_all_photo_urls():
    with patch("httpx.get", return_value=_mock_get(DETAIL_HTML)):
        detail = fetch_detail("mieszkanie-mokotow-ID12345")
    assert len(detail["photos"]) == 5
    assert detail["photos"][0] == "https://img.example.com/d1.jpg"


def test_fetch_detail_requests_correct_url():
    with patch("httpx.get", return_value=_mock_get(DETAIL_HTML)) as mock_get:
        fetch_detail("mieszkanie-mokotow-ID12345")
    call_url = mock_get.call_args[0][0]
    assert call_url == "https://www.otodom.pl/pl/oferta/mieszkanie-mokotow-ID12345"
