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
