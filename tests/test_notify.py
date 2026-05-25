from unittest.mock import patch, MagicMock
from src.notify import send_telegram, _build_caption

LISTING = {
    "title": "Mieszkanie 3-pok. z balkonem",
    "price": 3200,
    "area": 65,
    "rooms": "3",
    "city": "Warszawa",
    "district": "Mokotów",
    "url": "https://www.otodom.pl/pl/oferta/mieszkanie-mokotow-ID12345",
}


def test_build_caption_includes_key_fields():
    caption = _build_caption(LISTING)
    assert "Mieszkanie 3-pok. z balkonem" in caption
    assert "3200" in caption
    assert "65" in caption
    assert "3" in caption
    assert "Warszawa" in caption
    assert "Mokotów" in caption
    assert "otodom.pl" in caption


def test_build_caption_max_1024_chars():
    long_listing = dict(LISTING, title="X" * 2000)
    assert len(_build_caption(long_listing)) <= 1024


def test_send_telegram_no_photos_uses_send_message():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        send_telegram("TOKEN", "123456", LISTING, [])
    assert "sendMessage" in mock_post.call_args[0][0]


def test_send_telegram_one_photo_uses_send_photo():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        send_telegram("TOKEN", "123456", LISTING, ["https://img.example.com/1.jpg"])
    assert "sendPhoto" in mock_post.call_args[0][0]


def test_send_telegram_multiple_photos_uses_send_media_group():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=mock_resp) as mock_post:
        send_telegram("TOKEN", "123456", LISTING, [
            "https://img.example.com/1.jpg",
            "https://img.example.com/2.jpg",
            "https://img.example.com/3.jpg",
        ])
    assert "sendMediaGroup" in mock_post.call_args[0][0]


def test_send_telegram_sends_at_most_3_photos():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    captured = {}

    def capture(url, **kwargs):
        captured["json"] = kwargs.get("json", {})
        return mock_resp

    with patch("httpx.post", side_effect=capture):
        send_telegram("TOKEN", "123456", LISTING,
                      [f"https://img.example.com/{i}.jpg" for i in range(10)])

    assert len(captured["json"]["media"]) == 3


def test_send_telegram_no_district_does_not_raise():
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    with patch("httpx.post", return_value=mock_resp):
        send_telegram("TOKEN", "123456", dict(LISTING, district=None), [])
