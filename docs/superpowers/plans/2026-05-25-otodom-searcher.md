# Otodom Searcher — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub Actions cron job that monitors Otodom.pl rental listings, filters by keyword whitelist/blacklist, and sends new matching listings to Telegram with photos every 2 hours.

**Architecture:** Python script reads `config.yml` (search URLs + keyword filters), fetches Otodom search pages by parsing `__NEXT_DATA__` JSON embedded in HTML (no auth, no browser), compares to `state/seen.json` to find new listings, fetches detail pages for full description + photos, applies text filters, and sends Telegram messages. GitHub Actions runs this every 2 hours and commits the updated `seen.json` back to the repo.

**Tech Stack:** Python 3.12, httpx (HTTP client), pyyaml (config), Telegram Bot API (raw HTTP, no SDK)

---

## File Map

| File | Responsibility |
|------|----------------|
| `config.yml` | User-editable: search URLs, keyword filters, Telegram secret names |
| `src/filters.py` | `text_check(text, must_contain, must_not_contain) → bool` |
| `src/otodom.py` | `fetch_search(url) → list[dict]`, `fetch_detail(slug) → dict` |
| `src/notify.py` | `send_telegram(token, chat_id, listing, photos)` via raw HTTP |
| `src/main.py` | Orchestrator: load config → run searches → update state |
| `state/seen.json` | JSON array of processed listing IDs (committed by Actions) |
| `.github/workflows/search.yml` | Cron schedule, run script, commit state back |
| `tests/test_filters.py` | Unit tests for text_check |
| `tests/test_otodom.py` | Tests using embedded HTML fixture strings (no real HTTP) |
| `tests/test_notify.py` | Tests with mocked httpx |
| `tests/test_main.py` | Integration tests with all external calls mocked |
| `requirements.txt` | httpx==0.27.*, pyyaml==6.* |
| `README.md` | Setup guide (bot token, chat_id, secrets, config) |

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `config.yml`
- Create: `state/seen.json`
- Create: `.gitignore`
- Create: `src/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
httpx==0.27.*
pyyaml==6.*
```

- [ ] **Step 2: Create requirements-dev.txt**

```
pytest==8.*
pytest-mock==3.*
```

- [ ] **Step 3: Create config.yml**

```yaml
telegram:
  token_env: TELEGRAM_TOKEN    # name of the GitHub Secret
  chat_id_env: TELEGRAM_CHAT_ID

searches:
  - name: warszawa-rent
    # Paste your Otodom search URL here (open otodom.pl, set filters, copy URL from browser)
    url: "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/mazowieckie/warszawa/warszawa/warszawa?limit=36"
    # At least ONE of these words must appear in title or description (case-insensitive substring)
    # Set to [] to disable whitelist filtering
    text_must_contain:
      - balkon
      - taras
      - ogród
    # Listing is skipped if ANY of these words appear (case-insensitive)
    # Set to [] to disable blacklist filtering
    text_must_not_contain:
      - kawalerka
      - parter
```

- [ ] **Step 4: Create state/seen.json**

```json
[]
```

- [ ] **Step 5: Create .gitignore**

```
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 6: Create empty init files**

```bash
mkdir -p src tests
touch src/__init__.py tests/__init__.py
```

- [ ] **Step 7: Install dependencies**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

- [ ] **Step 8: Verify pytest collects zero tests**

```bash
pytest --collect-only
```

Expected: `no tests ran`

- [ ] **Step 9: Commit**

```bash
git init
git add requirements.txt requirements-dev.txt config.yml state/seen.json .gitignore src/__init__.py tests/__init__.py
git commit -m "chore: project scaffold"
```

---

### Task 2: Text Filter

**Files:**
- Create: `src/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_filters.py`:

```python
from src.filters import text_check


def test_empty_rules_always_passes():
    assert text_check("any text at all", [], []) is True


def test_whitelist_match_substring():
    assert text_check("mieszkanie z balkonem w centrum", ["balkon"], []) is True


def test_whitelist_no_match():
    assert text_check("mieszkanie na piętrze bez udogodnień", ["balkon"], []) is False


def test_whitelist_multiple_words_or_logic():
    # at least ONE must match — not all
    assert text_check("piękny taras widokowy", ["balkon", "taras"], []) is True


def test_whitelist_empty_passes_any_text():
    assert text_check("kawalerka bez niczego", [], []) is True


def test_blacklist_skips_on_match():
    assert text_check("kawalerka z balkonem", [], ["kawalerka"]) is False


def test_blacklist_no_match_passes():
    assert text_check("trzypokojowe mieszkanie", [], ["kawalerka"]) is True


def test_whitelist_and_blacklist_blacklist_wins():
    # has whitelist word but also blacklist word → False
    assert text_check("jest balkon ale kawalerka", ["balkon"], ["kawalerka"]) is False


def test_case_insensitive_whitelist():
    assert text_check("Mieszkanie Z BALKONEM", ["balkon"], []) is True


def test_case_insensitive_blacklist():
    assert text_check("KAWALERKA w centrum", [], ["kawalerka"]) is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_filters.py -v
```

Expected: all 10 tests FAIL with `ImportError: cannot import name 'text_check'`

- [ ] **Step 3: Implement filters.py**

Create `src/filters.py`:

```python
def text_check(
    text: str,
    must_contain: list[str],
    must_not_contain: list[str],
) -> bool:
    lower = text.lower()
    if any(word.lower() in lower for word in must_not_contain):
        return False
    if must_contain and not any(word.lower() in lower for word in must_contain):
        return False
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_filters.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/filters.py tests/test_filters.py
git commit -m "feat: text whitelist/blacklist filter"
```

---

### Task 3: Otodom Search Scraper

**Files:**
- Create: `src/otodom.py`
- Create: `tests/test_otodom.py`

Otodom data structures (confirmed via live inspection):
- Search items at: `props.pageProps.data.searchAds.items`
- `id` is an integer → convert to str for JSON state storage
- `roomsNumber` is a string enum: `"ONE"`, `"TWO"`, `"THREE"`, `"FOUR"`, `"FIVE"`, `"SIX"`, `"SEVEN_OR_MORE"`
- Price: use `rentPrice.value` if > 0, else `totalPrice.value`
- District: find entry in `location.reverseGeocoding.locations` where `locationLevel == "district"`
- Image URLs: each image has `"large"` key (1280×1024)

- [ ] **Step 1: Write failing tests**

Create `tests/test_otodom.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_otodom.py -v
```

Expected: FAIL with `ImportError: cannot import name 'fetch_search'`

- [ ] **Step 3: Implement fetch_search in otodom.py**

Create `src/otodom.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_otodom.py::test_fetch_search_parses_listing \
       tests/test_otodom.py::test_fetch_search_uses_total_price_when_rent_is_zero \
       tests/test_otodom.py::test_fetch_search_district_none_when_missing -v
```

Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add src/otodom.py tests/test_otodom.py
git commit -m "feat: otodom search page scraper"
```

---

### Task 4: Otodom Detail Page Scraper

**Files:**
- Modify: `src/otodom.py` — append `_strip_html()` and `fetch_detail()`
- Modify: `tests/test_otodom.py` — append detail page tests

Detail page data at: `props.pageProps.ad.description` (HTML string) and `props.pageProps.ad.images[*].large`

- [ ] **Step 1: Append failing tests to tests/test_otodom.py**

```python
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
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
pytest tests/test_otodom.py::test_fetch_detail_strips_html_from_description \
       tests/test_otodom.py::test_fetch_detail_returns_all_photo_urls \
       tests/test_otodom.py::test_fetch_detail_requests_correct_url -v
```

Expected: FAIL with `ImportError: cannot import name 'fetch_detail'`

- [ ] **Step 3: Append fetch_detail to src/otodom.py**

```python
def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def fetch_detail(slug: str) -> dict:
    url = f"https://www.otodom.pl/pl/oferta/{slug}"
    response = httpx.get(url, headers=_HEADERS, follow_redirects=True, timeout=30)
    response.raise_for_status()
    data = _parse_next_data(response.text)
    ad = data["props"]["pageProps"]["ad"]
    description = _strip_html(ad.get("description", ""))
    photos = [img["large"] for img in ad.get("images", []) if img.get("large")]
    return {"description": description, "photos": photos}
```

- [ ] **Step 4: Run all otodom tests**

```bash
pytest tests/test_otodom.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/otodom.py tests/test_otodom.py
git commit -m "feat: otodom detail page scraper"
```

---

### Task 5: Telegram Notifier

**Files:**
- Create: `src/notify.py`
- Create: `tests/test_notify.py`

Telegram API methods used:
- `sendMessage` — no photos (text only)
- `sendPhoto` — exactly 1 photo
- `sendMediaGroup` — 2-3 photos as album (requires ≥2 items)

- [ ] **Step 1: Write failing tests**

Create `tests/test_notify.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_notify.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement notify.py**

Create `src/notify.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_notify.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/notify.py tests/test_notify.py
git commit -m "feat: telegram notifier"
```

---

### Task 6: Main Orchestrator

**Files:**
- Create: `src/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_main.py`:

```python
import json
import yaml
from pathlib import Path
from unittest.mock import patch

from src.main import load_seen, save_seen, run


def test_load_seen_empty_when_file_missing(tmp_path):
    assert load_seen(tmp_path / "seen.json") == set()


def test_load_seen_parses_existing_ids(tmp_path):
    f = tmp_path / "seen.json"
    f.write_text('["123", "456"]')
    assert load_seen(f) == {"123", "456"}


def test_save_seen_writes_sorted_json(tmp_path):
    f = tmp_path / "seen.json"
    save_seen({"789", "123", "456"}, f)
    assert json.loads(f.read_text()) == ["123", "456", "789"]


def _make_config(tmp_path, must_contain=None, must_not_contain=None) -> Path:
    cfg = tmp_path / "config.yml"
    config = {
        "telegram": {"token_env": "TG_TOKEN", "chat_id_env": "TG_CHAT_ID"},
        "searches": [{
            "name": "test",
            "url": "https://www.otodom.pl/...",
            "text_must_contain": must_contain or [],
            "text_must_not_contain": must_not_contain or [],
        }],
    }
    cfg.write_text(yaml.dump(config))
    return cfg


FAKE_ITEMS = [
    {"id": "111", "slug": "old-ID111", "title": "Old listing", "price": 1000,
     "area": 40, "rooms": "1", "city": "W", "district": None, "url": "u1"},
    {"id": "222", "slug": "new-ID222", "title": "New listing with balkon", "price": 2000,
     "area": 60, "rooms": "2", "city": "W", "district": None, "url": "u2"},
]
FAKE_DETAIL = {"description": "opis z balkonem", "photos": ["https://img.example.com/1.jpg"]}


def test_run_sends_only_new_listings(tmp_path):
    cfg = _make_config(tmp_path)
    seen_file = tmp_path / "seen.json"
    seen_file.write_text('["111"]')  # 111 already seen

    with patch("src.main.fetch_search", return_value=FAKE_ITEMS), \
         patch("src.main.fetch_detail", return_value=FAKE_DETAIL), \
         patch("src.main.send_telegram") as mock_send, \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file)

    mock_send.assert_called_once()
    assert mock_send.call_args[0][2]["id"] == "222"


def test_run_skips_listings_failing_text_filter(tmp_path):
    cfg = _make_config(tmp_path, must_contain=["balkon"])
    seen_file = tmp_path / "seen.json"
    seen_file.write_text("[]")

    # Title and description contain no "balkon" substring
    no_match_items = [{
        "id": "333", "slug": "no-match-ID333",
        "title": "Mieszkanie na piętrze", "price": 1500,
        "area": 45, "rooms": "2", "city": "W", "district": None, "url": "u3",
    }]
    no_match_detail = {"description": "opis bez żadnych udogodnień", "photos": []}

    with patch("src.main.fetch_search", return_value=no_match_items), \
         patch("src.main.fetch_detail", return_value=no_match_detail), \
         patch("src.main.send_telegram") as mock_send, \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file)

    mock_send.assert_not_called()
    # Listing marked seen so it won't be re-processed next run
    assert "333" in json.loads(seen_file.read_text())


def test_run_updates_seen_file(tmp_path):
    cfg = _make_config(tmp_path)
    seen_file = tmp_path / "seen.json"
    seen_file.write_text("[]")

    items = [{"id": "444", "slug": "listing-ID444", "title": "OK", "price": 2000,
               "area": 55, "rooms": "2", "city": "W", "district": None, "url": "u4"}]
    detail = {"description": "opis", "photos": []}

    with patch("src.main.fetch_search", return_value=items), \
         patch("src.main.fetch_detail", return_value=detail), \
         patch("src.main.send_telegram"), \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file)

    assert "444" in json.loads(seen_file.read_text())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_main.py -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement main.py**

Create `src/main.py`:

```python
import json
import os
from pathlib import Path

import yaml

from src.otodom import fetch_search, fetch_detail
from src.filters import text_check
from src.notify import send_telegram

_DEFAULT_CONFIG = Path("config.yml")
_DEFAULT_STATE = Path("state/seen.json")


def load_seen(state_file: Path = _DEFAULT_STATE) -> set[str]:
    if state_file.exists():
        return set(json.loads(state_file.read_text()))
    return set()


def save_seen(seen: set[str], state_file: Path = _DEFAULT_STATE) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(sorted(seen), indent=2))


def run(config_file: Path = _DEFAULT_CONFIG, state_file: Path = _DEFAULT_STATE) -> None:
    config = yaml.safe_load(config_file.read_text())
    token = os.environ[config["telegram"]["token_env"]]
    chat_id = os.environ[config["telegram"]["chat_id_env"]]
    seen = load_seen(state_file)
    new_seen = set(seen)

    for search in config["searches"]:
        items = fetch_search(search["url"])
        for item in items:
            lid = str(item["id"])
            if lid in seen:
                continue
            detail = fetch_detail(item["slug"])
            full_text = item["title"] + " " + detail["description"]
            if not text_check(
                full_text,
                search.get("text_must_contain", []),
                search.get("text_must_not_contain", []),
            ):
                new_seen.add(lid)
                continue
            send_telegram(token, chat_id, item, detail["photos"])
            new_seen.add(lid)
            print(f"Sent: {item['title']} ({lid})")

    save_seen(new_seen, state_file)


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run all tests**

```bash
pytest -v
```

Expected: all 28 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/main.py tests/test_main.py
git commit -m "feat: main orchestrator"
```

---

### Task 7: GitHub Actions Workflow

**Files:**
- Create: `.github/workflows/search.yml`

- [ ] **Step 1: Create workflow directory**

```bash
mkdir -p .github/workflows
```

- [ ] **Step 2: Create .github/workflows/search.yml**

```yaml
name: Search Otodom

on:
  schedule:
    - cron: '0 */2 * * *'   # every 2 hours
  workflow_dispatch:          # manual trigger for testing

jobs:
  search:
    runs-on: ubuntu-latest
    permissions:
      contents: write         # needed to commit seen.json back

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run search
        run: python src/main.py
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}

      - name: Commit updated state
        run: |
          git config user.name "otodom-bot"
          git config user.email "bot@users.noreply.github.com"
          git add state/seen.json
          git diff --staged --quiet || git commit -m "chore: update seen listings [skip ci]"
          git push
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/search.yml
git commit -m "ci: github actions cron every 2 hours"
```

---

### Task 8: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# Otodom Searcher

Monitors Otodom.pl for new rental listings every 2 hours and sends matches to Telegram with photos.

No API costs — only GitHub Actions (free tier) and a free Telegram bot.

## Setup (~10 minutes)

### 1. Create Telegram Bot

1. Open Telegram → search `@BotFather` → send `/newbot`
2. Follow prompts → copy the **bot token**
3. Search for your new bot by username → tap **Start**
4. Run in terminal (replace TOKEN with your actual token):
   ```bash
   curl -s "https://api.telegram.org/botTOKEN/getUpdates" | python3 -m json.tool
   ```
5. Find `"chat": {"id": XXXXXXX}` — that number is your **TELEGRAM_CHAT_ID**

### 2. Fork & Configure

1. Fork this repository on GitHub
2. Edit `config.yml`:
   - Open [otodom.pl](https://www.otodom.pl), set your filters in the UI, copy the URL from the browser
   - Paste it into the `url:` field
   - Edit `text_must_contain` and `text_must_not_contain` lists

### 3. Add GitHub Secrets

Go to your fork: **Settings → Secrets and variables → Actions → New repository secret**

| Secret name | Value |
|-------------|-------|
| `TELEGRAM_TOKEN` | Bot token from @BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID from getUpdates (e.g. `264743781`) |

### 4. Test Manually

**Actions → Search Otodom → Run workflow**

You should receive Telegram messages within ~30 seconds for any listings matching your filters.

---

## Config Reference

```yaml
telegram:
  token_env: TELEGRAM_TOKEN    # GitHub Secret name — do not change
  chat_id_env: TELEGRAM_CHAT_ID

searches:
  - name: my-search            # label shown in logs
    url: "https://www.otodom.pl/pl/wyniki/wynajem/..."
    text_must_contain:         # at least ONE must appear (case-insensitive substring)
      - balkon                 # set to [] to disable
    text_must_not_contain:     # listing skipped if ANY appears
      - kawalerka              # set to [] to disable
```

You can add multiple searches under `searches:`.

## How It Works

1. Every 2 hours GitHub Actions fetches your Otodom search URL
2. Listing IDs not in `state/seen.json` are new — their detail pages are fetched
3. Text filters applied: skip if blacklist word found, skip if whitelist non-empty and no match
4. Matching listings sent to Telegram with up to 3 photos, price, area, rooms, and link
5. All processed IDs saved to `state/seen.json` (committed back to the repo automatically)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: setup guide"
```

---

### Task 9: End-to-End Verification

- [ ] **Step 1: Run full test suite**

```bash
pytest -v
```

Expected output (28 tests):
```
tests/test_filters.py::test_empty_rules_always_passes PASSED
tests/test_filters.py::test_whitelist_match_substring PASSED
tests/test_filters.py::test_whitelist_no_match PASSED
tests/test_filters.py::test_whitelist_multiple_words_or_logic PASSED
tests/test_filters.py::test_whitelist_empty_passes_any_text PASSED
tests/test_filters.py::test_blacklist_skips_on_match PASSED
tests/test_filters.py::test_blacklist_no_match_passes PASSED
tests/test_filters.py::test_whitelist_and_blacklist_blacklist_wins PASSED
tests/test_filters.py::test_case_insensitive_whitelist PASSED
tests/test_filters.py::test_case_insensitive_blacklist PASSED
tests/test_otodom.py::test_fetch_search_parses_listing PASSED
tests/test_otodom.py::test_fetch_search_uses_total_price_when_rent_is_zero PASSED
tests/test_otodom.py::test_fetch_search_district_none_when_missing PASSED
tests/test_otodom.py::test_fetch_detail_strips_html_from_description PASSED
tests/test_otodom.py::test_fetch_detail_returns_all_photo_urls PASSED
tests/test_otodom.py::test_fetch_detail_requests_correct_url PASSED
tests/test_notify.py::test_build_caption_includes_key_fields PASSED
tests/test_notify.py::test_build_caption_max_1024_chars PASSED
tests/test_notify.py::test_send_telegram_no_photos_uses_send_message PASSED
tests/test_notify.py::test_send_telegram_one_photo_uses_send_photo PASSED
tests/test_notify.py::test_send_telegram_multiple_photos_uses_send_media_group PASSED
tests/test_notify.py::test_send_telegram_sends_at_most_3_photos PASSED
tests/test_notify.py::test_send_telegram_no_district_does_not_raise PASSED
tests/test_main.py::test_load_seen_empty_when_file_missing PASSED
tests/test_main.py::test_load_seen_parses_existing_ids PASSED
tests/test_main.py::test_save_seen_writes_sorted_json PASSED
tests/test_main.py::test_run_sends_only_new_listings PASSED
tests/test_main.py::test_run_skips_listings_failing_text_filter PASSED
tests/test_main.py::test_run_updates_seen_file PASSED
29 passed
```

- [ ] **Step 2: Dry-run scraper with live Otodom URL**

```bash
TELEGRAM_TOKEN=dummy TELEGRAM_CHAT_ID=dummy python3 -c "
from src.otodom import fetch_search
items = fetch_search('https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/mazowieckie/warszawa/warszawa/warszawa?limit=36')
print(f'Found {len(items)} listings')
print(items[0])
"
```

Expected: prints 30-36 listings, first item has id/title/price/area/rooms/city/district/url fields.

- [ ] **Step 3: Push to GitHub**

```bash
git push origin main
```

- [ ] **Step 4: Add GitHub Secrets**

GitHub → your fork → Settings → Secrets and variables → Actions:
- `TELEGRAM_TOKEN` — your bot token from @BotFather
- `TELEGRAM_CHAT_ID` — `264743781`

- [ ] **Step 5: Reset state and run workflow manually**

```bash
echo '[]' > state/seen.json
git add state/seen.json
git commit -m "chore: reset seen for first run"
git push
```

Then: GitHub → Actions → "Search Otodom" → **Run workflow**

Expected: Telegram messages arrive for all listings matching your `config.yml` filters.
