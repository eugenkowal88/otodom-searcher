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
