from pathlib import Path
from src.commands import _cmd_add, _cmd_remove, _cmd_block, _cmd_unblock, _normalize_words


def _make_config():
    return {
        "telegram": {"token_env": "T", "chat_id_env": "C"},
        "searches": [{
            "name": "test",
            "url": "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/mazowieckie/warszawa/warszawa/warszawa?limit=36",
            "text_must_contain": ["balkon"],
            "text_must_not_contain": ["kawalerka"],
        }],
    }


def test_normalize_words_handles_spaces_and_commas():
    assert _normalize_words("balkon taras") == ["balkon", "taras"]
    assert _normalize_words("balkon, taras") == ["balkon", "taras"]
    assert _normalize_words("BALKON, Taras  ogród") == ["balkon", "taras", "ogród"]
    assert _normalize_words("") == []
    assert _normalize_words("   ") == []


def test_cmd_add_appends_new_word():
    config = _make_config()
    reply = _cmd_add("taras", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_contain"] == ["balkon", "taras"]
    assert "taras" in reply.lower()


def test_cmd_add_dedupes_existing():
    config = _make_config()
    reply = _cmd_add("balkon", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_contain"] == ["balkon"]
    assert "already" in reply.lower() or "dedup" in reply.lower() or "0" in reply


def test_cmd_add_multiple_at_once():
    config = _make_config()
    _cmd_add("taras, ogród", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_contain"] == ["balkon", "taras", "ogród"]


def test_cmd_remove_removes_existing():
    config = _make_config()
    reply = _cmd_remove("balkon", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_contain"] == []
    assert "balkon" in reply.lower()


def test_cmd_remove_ignores_missing():
    config = _make_config()
    reply = _cmd_remove("nieistnieje", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_contain"] == ["balkon"]


def test_cmd_block_appends_to_blacklist():
    config = _make_config()
    _cmd_block("parter", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_not_contain"] == ["kawalerka", "parter"]


def test_cmd_unblock_removes_from_blacklist():
    config = _make_config()
    _cmd_unblock("kawalerka", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["text_must_not_contain"] == []
