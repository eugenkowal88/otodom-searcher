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
FAKE_DETAIL = {
    "description": "opis z balkonem",
    "photos": ["https://img.example.com/1.jpg"],
    "rent": "500 zł",
    "deposit": "4 000 zł",
    "advertiser_type": "business",
    "agency_name": "Fake Agency",
}


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
    no_match_detail = {
        "description": "opis bez żadnych udogodnień",
        "photos": [],
        "rent": None,
        "deposit": None,
        "advertiser_type": "private",
        "agency_name": None,
    }

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
    detail = {
        "description": "opis",
        "photos": [],
        "rent": None,
        "deposit": None,
        "advertiser_type": "private",
        "agency_name": None,
    }

    with patch("src.main.fetch_search", return_value=items), \
         patch("src.main.fetch_detail", return_value=detail), \
         patch("src.main.send_telegram"), \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file)

    assert "444" in json.loads(seen_file.read_text())


def test_run_passes_detail_fields_to_send_telegram(tmp_path):
    cfg = _make_config(tmp_path)
    seen_file = tmp_path / "seen.json"
    seen_file.write_text("[]")  # empty — both FAKE_ITEMS will be processed

    with patch("src.main.fetch_search", return_value=FAKE_ITEMS), \
         patch("src.main.fetch_detail", return_value=FAKE_DETAIL), \
         patch("src.main.send_telegram") as mock_send, \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file)

    assert mock_send.called
    sent_listing = mock_send.call_args_list[0][0][2]
    assert sent_listing["rent"] == "500 zł"
    assert sent_listing["deposit"] == "4 000 zł"
    assert sent_listing["advertiser_type"] == "business"
    assert sent_listing["agency_name"] == "Fake Agency"


def test_run_skips_when_paused(tmp_path):
    cfg = _make_config(tmp_path)
    seen_file = tmp_path / "seen.json"
    seen_file.write_text("[]")
    bot_state_file = tmp_path / "bot_state.json"
    bot_state_file.write_text('{"last_update_id": 0, "paused": true}')

    with patch("src.main.fetch_search") as mock_fetch, \
         patch("src.main.send_telegram") as mock_send, \
         patch.dict("os.environ", {"TG_TOKEN": "tok", "TG_CHAT_ID": "999"}):
        run(config_file=cfg, state_file=seen_file, bot_state_file=bot_state_file)

    mock_fetch.assert_not_called()
    mock_send.assert_not_called()
