import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

import httpx
import yaml
from src.notify import send_text


def _normalize_words(raw: str) -> list[str]:
    parts = re.split(r"[\s,]+", raw.strip())
    return [p.lower() for p in parts if p]


def _cmd_add(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    words = _normalize_words(args)
    if not words:
        return "Usage: /add <word> [word ...]"
    lst = config["searches"][0].setdefault("text_must_contain", [])
    added = []
    for w in words:
        if w not in lst:
            lst.append(w)
            added.append(w)
    if not added:
        return f"All already in whitelist. Whitelist now: {len(lst)} words"
    return f"Added: {', '.join(added)} (whitelist now: {len(lst)} words)"


def _cmd_remove(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    words = _normalize_words(args)
    if not words:
        return "Usage: /remove <word> [word ...]"
    lst = config["searches"][0].setdefault("text_must_contain", [])
    removed = [w for w in words if w in lst]
    config["searches"][0]["text_must_contain"] = [w for w in lst if w not in removed]
    if not removed:
        return "Nothing to remove."
    new_count = len(config["searches"][0]["text_must_contain"])
    return f"Removed: {', '.join(removed)} (whitelist now: {new_count} words)"


def _cmd_block(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    words = _normalize_words(args)
    if not words:
        return "Usage: /block <word> [word ...]"
    lst = config["searches"][0].setdefault("text_must_not_contain", [])
    added = []
    for w in words:
        if w not in lst:
            lst.append(w)
            added.append(w)
    if not added:
        return f"All already in blacklist. Blacklist now: {len(lst)} words"
    return f"Blocked: {', '.join(added)} (blacklist now: {len(lst)} words)"


def _cmd_unblock(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    words = _normalize_words(args)
    if not words:
        return "Usage: /unblock <word> [word ...]"
    lst = config["searches"][0].setdefault("text_must_not_contain", [])
    removed = [w for w in words if w in lst]
    config["searches"][0]["text_must_not_contain"] = [w for w in lst if w not in removed]
    if not removed:
        return "Nothing to unblock."
    new_count = len(config["searches"][0]["text_must_not_contain"])
    return f"Unblocked: {', '.join(removed)} (blacklist now: {new_count} words)"


_POLISH_MAP = str.maketrans({
    "ł": "l", "ó": "o", "ą": "a", "ę": "e",
    "ś": "s", "ć": "c", "ż": "z", "ź": "z", "ń": "n",
})

_ROOMS_MAP = {
    1: "ONE", 2: "TWO", 3: "THREE",
    4: "FOUR", 5: "FIVE", 6: "SIX",
}


def _slugify(name: str) -> str:
    return name.strip().lower().translate(_POLISH_MAP).replace(" ", "-")


def _set_query_param(url: str, key: str, value: str) -> str:
    parts = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    qs.append((key, value))
    return urlunparse(parts._replace(query=urlencode(qs)))


def _remove_query_param(url: str, key: str) -> str:
    parts = urlparse(url)
    qs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key]
    return urlunparse(parts._replace(query=urlencode(qs)))


def _cmd_seturl(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    url = args.strip()
    if not url.startswith("https://www.otodom.pl/"):
        return "URL must start with https://www.otodom.pl/"
    config["searches"][0]["url"] = url
    return "URL set."


def _cmd_price(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    spec = args.strip()
    if not spec:
        return "Usage: /price 3400 or /price 2000-3400"
    url = config["searches"][0]["url"]
    if "-" in spec:
        try:
            lo, hi = [int(x) for x in spec.split("-", 1)]
        except ValueError:
            return "Invalid number. Usage: /price 3400 or /price 2000-3400"
        url = _set_query_param(url, "priceMin", str(lo))
        url = _set_query_param(url, "priceMax", str(hi))
        config["searches"][0]["url"] = url
        return f"priceMin={lo}, priceMax={hi} applied"
    try:
        hi = int(spec)
    except ValueError:
        return "Invalid number. Usage: /price 3400 or /price 2000-3400"
    url = _set_query_param(url, "priceMax", str(hi))
    config["searches"][0]["url"] = url
    return f"priceMax={hi} applied"


def _cmd_rooms(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    try:
        n = int(args.strip())
    except ValueError:
        return "Invalid number. Usage: /rooms 2"
    if n not in _ROOMS_MAP:
        return "Supported: 1-6"
    enum = _ROOMS_MAP[n]
    url = _set_query_param(config["searches"][0]["url"], "roomsNumber", f"[{enum}]")
    config["searches"][0]["url"] = url
    return f"roomsNumber={enum} applied"


def _cmd_district(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    names = [_slugify(n) for n in re.split(r"[\s,]+", args.strip()) if n.strip()]
    if not names:
        return "Usage: /district <name> [name ...]"

    url = config["searches"][0]["url"]
    parts = urlparse(url)
    path_segments = parts.path.split("/")
    try:
        property_idx = next(
            i for i, seg in enumerate(path_segments)
            if seg in ("mieszkanie", "dom", "dzialka", "lokal", "garaz")
        )
    except StopIteration:
        return "Cannot determine city from current URL. Use /seturl with a full Warsaw search URL first."

    city_segments = path_segments[property_idx + 1 : property_idx + 5]
    if len(city_segments) < 4 or not all(city_segments):
        return "Cannot determine city from current URL. Use /seturl with a full Warsaw search URL first."

    prefix = "/".join(city_segments)
    location_ids = ",".join(f"{prefix}/{d}" for d in names)
    locations_value = f"[{location_ids}]"

    new_path = "/".join(path_segments[: property_idx + 5])

    new_parts = parts._replace(path=new_path)
    url_no_locations = _remove_query_param(urlunparse(new_parts), "locations")
    url_final = _set_query_param(url_no_locations, "locations", locations_value)
    config["searches"][0]["url"] = url_final
    return f"Filtering districts: {', '.join(names)}"


def _cmd_pause(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    bot_state["paused"] = True
    return "Paused — search will skip until /resume."


def _cmd_resume(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    bot_state["paused"] = False
    return "Resumed."


def _cmd_reset(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    seen_file.parent.mkdir(parents=True, exist_ok=True)
    seen_file.write_text("[]")
    return "seen cleared — next run will treat all matching listings as new."


def _cmd_help(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    return (
        "Commands:\n"
        "/help — this list\n"
        "/status — current config\n"
        "/add <words> — add to whitelist (e.g. /add balkon taras)\n"
        "/remove <words> — remove from whitelist\n"
        "/block <words> — add to blacklist\n"
        "/unblock <words> — remove from blacklist\n"
        "/seturl <url> — replace Otodom search URL\n"
        "/price 3400 or /price 2000-3400 — set price range\n"
        "/rooms 2 — filter to 2 rooms (1-6)\n"
        "/district <names> — filter to districts (e.g. /district mokotow bielany)\n"
        "/pause — stop notifications\n"
        "/resume — start again\n"
        "/reset — clear seen listings"
    )


def _cmd_status(args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    search = config["searches"][0]
    seen_count = 0
    if seen_file.exists():
        seen_count = len(json.loads(seen_file.read_text()))
    state = "PAUSED" if bot_state.get("paused") else "active"
    whitelist = ", ".join(search.get("text_must_contain", [])) or "(empty)"
    blacklist = ", ".join(search.get("text_must_not_contain", [])) or "(empty)"
    return (
        f"Status: {state}\n"
        f"URL: {search['url']}\n"
        f"Whitelist: {whitelist}\n"
        f"Blacklist: {blacklist}\n"
        f"Seen: {seen_count} listings"
    )


_HANDLERS = {
    "add": _cmd_add,
    "remove": _cmd_remove,
    "block": _cmd_block,
    "unblock": _cmd_unblock,
    "seturl": _cmd_seturl,
    "price": _cmd_price,
    "rooms": _cmd_rooms,
    "district": _cmd_district,
    "pause": _cmd_pause,
    "resume": _cmd_resume,
    "reset": _cmd_reset,
    "help": _cmd_help,
    "start": _cmd_help,
    "status": _cmd_status,
}


def _handle_command(cmd: str, args: str, config: dict, bot_state: dict, seen_file: Path) -> str:
    handler = _HANDLERS.get(cmd)
    if not handler:
        return "Unknown command. Try /help"
    try:
        return handler(args, config, bot_state, seen_file)
    except Exception as e:
        return f"Error: {e}"


def _parse_command(text: str) -> tuple[str, str] | None:
    if not text.startswith("/"):
        return None
    body = text[1:].split(maxsplit=1)
    if not body:
        return None
    cmd = body[0].lower()
    cmd = cmd.split("@", 1)[0]
    args = body[1] if len(body) > 1 else ""
    return cmd, args


def poll_and_process(
    token: str,
    chat_id: int,
    config_file: Path,
    bot_state_file: Path,
    seen_file: Path,
) -> None:
    bot_state = json.loads(bot_state_file.read_text()) if bot_state_file.exists() else {"last_update_id": 0, "paused": False}
    config = yaml.safe_load(config_file.read_text())

    last_id = bot_state.get("last_update_id", 0)
    response = httpx.get(
        f"https://api.telegram.org/bot{token}/getUpdates",
        params={"offset": last_id + 1, "timeout": 0},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    updates = payload.get("result", [])

    if not updates:
        return

    try:
        for update in updates:
            update_id = update["update_id"]
            bot_state["last_update_id"] = max(bot_state.get("last_update_id", 0), update_id)

            message = update.get("message") or {}
            sender_chat = message.get("chat", {}).get("id")
            text = message.get("text", "")

            if sender_chat != chat_id:
                continue

            parsed = _parse_command(text)
            if not parsed:
                continue
            cmd, args = parsed
            reply = _handle_command(cmd, args, config, bot_state, seen_file)
            send_text(token, chat_id, reply)
    finally:
        config_file.write_text(yaml.dump(config, allow_unicode=True, sort_keys=False))
        bot_state_file.write_text(json.dumps(bot_state, indent=2))


if __name__ == "__main__":
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_CHAT_ID"])
    poll_and_process(
        token=token,
        chat_id=chat_id,
        config_file=Path("config.yml"),
        bot_state_file=Path("state/bot_state.json"),
        seen_file=Path("state/seen.json"),
    )
