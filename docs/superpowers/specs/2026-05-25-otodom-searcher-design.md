# Otodom Searcher — Design Spec

**Date:** 2026-05-25  
**Status:** Approved

## Overview

A GitHub Actions cron job that monitors Otodom.pl rental listings, filters by text keywords, and sends new matching listings to a Telegram bot with photos.

No external AI APIs required. Zero cost beyond GitHub Actions free tier.

## Goals

- Notify about new Otodom listings within ~2 hours of them appearing
- Filter by user-defined keyword whitelist and blacklist on title + description
- Send Telegram message with photos, price, area, rooms, and link
- Never send the same listing twice
- Require minimal maintenance — change a config.yml, done

## Non-Goals

- AI/vision analysis of photos (may be added later with Gemini free tier)
- Web UI or dashboard
- Multiple users / multi-tenant

## Architecture

### Data Flow

```
config.yml (search URLs + keyword filters)
        │
[GitHub Actions — cron every 2 hours]
        │
        ├─► otodom.fetch_search(url)
        │     └─ GET Otodom search page HTML
        │     └─ parse __NEXT_DATA__ JSON → items[] (id, slug, title, price, area, rooms, images)
        │
        ├─► filter: id ∉ state/seen.json → only new listings
        │
        ├─► for each new listing:
        │     ├─ otodom.fetch_detail(slug)
        │     │     └─ GET detail page HTML → parse __NEXT_DATA__
        │     │     └─ extract: description, all photo URLs
        │     │
        │     ├─ filters.text_check(title + description, whitelist, blacklist)
        │     │     └─ skip if: whitelist non-empty AND no whitelist word found
        │     │     └─ skip if: any blacklist word found
        │     │
        │     └─ notify.send_telegram(listing_data, photo_urls[:3])
        │           └─ sendMediaGroup (3 photos as album)
        │           └─ caption: title, price, area, rooms, location, link
        │
        └─► append new IDs to state/seen.json
              └─ git commit + push (Actions bot commit)
```

### Repository Structure

```
otodom-searcher/
├── config.yml                     # user-editable: searches, filters, telegram config
├── src/
│   ├── main.py                    # orchestrator: load config → run searches → update state
│   ├── otodom.py                  # fetch_search(), fetch_detail() — Otodom scraping
│   ├── filters.py                 # text_check(text, must_contain, must_not_contain) → bool
│   └── notify.py                  # send_telegram(listing, photos) → uses raw HTTP
├── state/
│   └── seen.json                  # ["id1", "id2", ...] — committed back by Actions
├── .github/
│   └── workflows/
│       └── search.yml             # cron schedule + run + commit state
├── requirements.txt               # httpx only
└── README.md                      # setup guide (bot token, chat_id, secrets)
```

## Config Format

```yaml
telegram:
  token_env: TELEGRAM_TOKEN      # name of GitHub Secret
  chat_id_env: TELEGRAM_CHAT_ID  # name of GitHub Secret

searches:
  - name: warszawa-rent           # label for logs
    url: "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/..."
    # Whitelist: at least ONE word must appear in title or description
    # Leave empty [] to disable whitelist filtering
    text_must_contain:
      - balkon
      - taras
      - ogród
    # Blacklist: listing is skipped if ANY word appears
    # Leave empty [] to disable blacklist filtering
    text_must_not_contain:
      - kawalerka
      - parter
      - bez balkonu
```

## Component Details

### `otodom.py`

**`fetch_search(url) → list[dict]`**
- GET request with desktop User-Agent header (no auth required)
- Parse `<script id="__NEXT_DATA__">` JSON
- Path: `props.pageProps.data.searchAds.items`
- Returns list of: `{id, slug, title, totalPrice, rentPrice, areaInSquareMeters, roomsNumber, location, images}`
- Handles pagination: if URL has no `page=` param, only page 1 (sufficient for cron every 2 hours)

**`fetch_detail(slug) → dict`**
- GET `https://www.otodom.pl/pl/oferta/{slug}`
- Parse `__NEXT_DATA__` → extract description text + all image URLs
- Returns: `{description, photos: [url, ...]}`

### `filters.py`

**`text_check(text, must_contain, must_not_contain) → bool`**
- `text` = `title + " " + description` (lowercased)
- Whitelist: if `must_contain` is non-empty → at least one item must appear as substring
- Blacklist: if any item in `must_not_contain` appears → return False
- Case-insensitive, Polish characters handled (no normalization needed — matching substrings)

### `notify.py`

**`send_telegram(token, chat_id, listing, photo_urls) → None`**
- Uses `sendMediaGroup` with up to 3 photos
- Caption on first photo (Telegram limit: 1024 chars):
  ```
  🏠 {title}
  💰 {rent_price} zł/mies • 📐 {area} m² • 🛏 {rooms} pok.
  📍 {city}, {district}
  🔗 {url}
  ```
- Falls back to `sendMessage` (no photo) if photo_urls is empty
- Raises on HTTP error (Actions will report failure)

### `main.py`

```
load config.yml
load state/seen.json (or [] if missing)
for each search in config:
    items = fetch_search(url)
    new_items = [i for i in items if i['id'] not in seen_set]
    for item in new_items:
        detail = fetch_detail(item['slug'])
        if not text_check(item['title'] + detail['description'], ...):
            continue
        send_telegram(item, detail['photos'])
        seen_set.add(item['id'])
save state/seen.json
```

### `.github/workflows/search.yml`

```yaml
on:
  schedule:
    - cron: '0 */2 * * *'
  workflow_dispatch:              # manual run for testing

jobs:
  search:
    runs-on: ubuntu-latest
    permissions:
      contents: write             # needed to commit seen.json
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install -r requirements.txt
      - run: python src/main.py
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
      - name: Commit state
        run: |
          git config user.name "otodom-bot"
          git config user.email "bot@noreply"
          git add state/seen.json
          git diff --staged --quiet || git commit -m "chore: update seen listings"
          git push
```

## State Management

- `state/seen.json` is a JSON array of listing ID strings
- Committed back to the repo after every run (even if no new listings found — only if changed)
- On first run, file may not exist → treated as empty set
- IDs never expire (listings don't get re-announced)
- Worst case: if two Actions runs overlap (unlikely at 20 min), duplicate Telegram message — acceptable

## Error Handling

- Otodom fetch fails (rate limit, network): exception propagates → Actions run fails → user sees red X in GitHub
- Telegram send fails: exception propagates → run fails, state not committed (listing will retry next run)
- Detail fetch fails for one listing: log warning, skip that listing, continue

## Dependencies

```
httpx==0.27.*    # async-capable HTTP client, handles redirects cleanly
```

Python stdlib only otherwise (`json`, `os`, `re`). PyYAML for config parsing.

```
httpx==0.27.*
pyyaml==6.*
```

## Setup Checklist (for README)

1. Create bot via @BotFather → copy token
2. Send `/start` to bot → `curl .../getUpdates` → copy `chat.id`
3. Fork/clone repo, edit `config.yml` with your Otodom search URL and keywords
4. Push to GitHub
5. Settings → Secrets → add `TELEGRAM_TOKEN` and `TELEGRAM_CHAT_ID`
6. Actions → search.yml → Run workflow (manual trigger to test)

## Telegram Credentials

- Bot: `@otodom_searcher_bot`
- Chat ID: `264743781` — store as `TELEGRAM_CHAT_ID` secret
- Token: stored only in GitHub Secrets as `TELEGRAM_TOKEN`
