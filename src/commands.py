import json
import os
import re
from pathlib import Path


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
