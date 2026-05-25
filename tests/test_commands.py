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


from src.commands import _slugify, _cmd_seturl, _cmd_price, _cmd_rooms, _cmd_district


def test_slugify_basic():
    assert _slugify("Mokotow") == "mokotow"
    assert _slugify("  Bielany  ") == "bielany"


def test_slugify_polish_chars():
    assert _slugify("Mokotów") == "mokotow"
    assert _slugify("Śródmieście") == "srodmiescie"
    assert _slugify("Żoliborz") == "zoliborz"
    assert _slugify("Wąsk") == "wask"


def test_slugify_spaces_to_hyphens():
    assert _slugify("Stary Mokotów") == "stary-mokotow"


def test_cmd_seturl_accepts_otodom():
    config = _make_config()
    new_url = "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/mazowieckie/warszawa/warszawa/warszawa/mokotow"
    reply = _cmd_seturl(new_url, config, {}, Path("/tmp/x"))
    assert config["searches"][0]["url"] == new_url
    assert "set" in reply.lower()


def test_cmd_seturl_rejects_non_otodom():
    config = _make_config()
    original = config["searches"][0]["url"]
    reply = _cmd_seturl("https://example.com/foo", config, {}, Path("/tmp/x"))
    assert config["searches"][0]["url"] == original
    assert "otodom.pl" in reply.lower()


def test_cmd_price_max_only():
    config = _make_config()
    reply = _cmd_price("3400", config, {}, Path("/tmp/x"))
    assert "priceMax=3400" in config["searches"][0]["url"]
    assert "3400" in reply


def test_cmd_price_range():
    config = _make_config()
    _cmd_price("2000-3400", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert "priceMin=2000" in url
    assert "priceMax=3400" in url


def test_cmd_price_replaces_existing():
    config = _make_config()
    _cmd_price("3000", config, {}, Path("/tmp/x"))
    _cmd_price("4000", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert url.count("priceMax=") == 1
    assert "priceMax=4000" in url


def test_cmd_price_invalid():
    config = _make_config()
    reply = _cmd_price("abc", config, {}, Path("/tmp/x"))
    assert "invalid" in reply.lower() or "usage" in reply.lower()


def test_cmd_rooms_valid():
    config = _make_config()
    _cmd_rooms("2", config, {}, Path("/tmp/x"))
    assert "roomsNumber=%5BTWO%5D" in config["searches"][0]["url"]


def test_cmd_rooms_invalid_high():
    config = _make_config()
    reply = _cmd_rooms("7", config, {}, Path("/tmp/x"))
    assert "1-6" in reply


def test_cmd_rooms_non_numeric():
    config = _make_config()
    reply = _cmd_rooms("abc", config, {}, Path("/tmp/x"))
    assert "invalid" in reply.lower() or "usage" in reply.lower()


def test_cmd_district_single():
    config = _make_config()
    _cmd_district("mokotow", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert "locations=" in url
    assert "mokotow" in url


def test_cmd_district_multi():
    config = _make_config()
    _cmd_district("mokotow bielany", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert "mokotow" in url
    assert "bielany" in url
    assert url.count("locations=") == 1


def test_cmd_district_slugifies_polish():
    config = _make_config()
    _cmd_district("Mokotów, Śródmieście", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert "mokotow" in url
    assert "srodmiescie" in url


def test_cmd_district_replaces_existing_locations():
    config = _make_config()
    _cmd_district("mokotow", config, {}, Path("/tmp/x"))
    _cmd_district("bielany", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    assert "bielany" in url
    assert "mokotow" not in url
    assert url.count("locations=") == 1


def test_cmd_district_strips_district_from_path():
    config = _make_config()
    config["searches"][0]["url"] = (
        "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/"
        "mazowieckie/warszawa/warszawa/warszawa/mokotow?limit=36"
    )
    _cmd_district("bielany", config, {}, Path("/tmp/x"))
    url = config["searches"][0]["url"]
    path_part = url.split("?")[0]
    assert not path_part.endswith("/mokotow")
    assert "bielany" in url


def test_cmd_district_errors_on_short_path():
    config = _make_config()
    config["searches"][0]["url"] = "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie?foo=bar"
    reply = _cmd_district("mokotow", config, {}, Path("/tmp/x"))
    assert "cannot determine city" in reply.lower()
