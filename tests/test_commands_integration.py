import json
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.commands import poll_and_process


def _make_config_file(tmp_path) -> Path:
    cfg = tmp_path / "config.yml"
    cfg.write_text(yaml.dump({
        "telegram": {"token_env": "TG_TOKEN", "chat_id_env": "TG_CHAT_ID"},
        "searches": [{
            "name": "test",
            "url": "https://www.otodom.pl/pl/wyniki/wynajem/mieszkanie/mazowieckie/warszawa/warszawa/warszawa",
            "text_must_contain": [],
            "text_must_not_contain": [],
        }],
    }))
    return cfg


def _make_state(tmp_path, last_update_id=0, paused=False) -> Path:
    f = tmp_path / "bot_state.json"
    f.write_text(json.dumps({"last_update_id": last_update_id, "paused": paused}))
    return f


def _make_seen(tmp_path) -> Path:
    f = tmp_path / "seen.json"
    f.write_text("[]")
    return f


def _build_update(update_id: int, chat_id: int, text: str) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": chat_id, "first_name": "U"},
            "chat": {"id": chat_id, "type": "private"},
            "date": 1779700000,
            "text": text,
        },
    }


def _mock_response(json_data):
    r = MagicMock()
    r.raise_for_status = MagicMock()
    r.json = MagicMock(return_value=json_data)
    return r


def test_poll_processes_authorized_command_and_updates_config(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": [_build_update(100, 555, "/add taras")]}

    with patch("httpx.get", return_value=_mock_response(updates)), \
         patch("httpx.post", return_value=_mock_response({"ok": True})) as mock_post:
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    new_cfg = yaml.safe_load(cfg.read_text())
    assert "taras" in new_cfg["searches"][0]["text_must_contain"]

    assert mock_post.called
    sent_url = mock_post.call_args[0][0]
    assert "sendMessage" in sent_url

    new_state = json.loads(state.read_text())
    assert new_state["last_update_id"] == 100


def test_poll_ignores_unauthorized_chat(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": [_build_update(101, 999, "/add taras")]}

    with patch("httpx.get", return_value=_mock_response(updates)), \
         patch("httpx.post") as mock_post:
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    new_cfg = yaml.safe_load(cfg.read_text())
    assert "taras" not in new_cfg["searches"][0]["text_must_contain"]

    mock_post.assert_not_called()

    new_state = json.loads(state.read_text())
    assert new_state["last_update_id"] == 101


def test_poll_handles_empty_updates(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path, last_update_id=50)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": []}

    with patch("httpx.get", return_value=_mock_response(updates)), \
         patch("httpx.post") as mock_post:
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    mock_post.assert_not_called()
    new_state = json.loads(state.read_text())
    assert new_state["last_update_id"] == 50


def test_poll_processes_multiple_commands_in_order(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": [
        _build_update(10, 555, "/add balkon"),
        _build_update(11, 555, "/add taras"),
        _build_update(12, 555, "/block kawalerka"),
    ]}

    with patch("httpx.get", return_value=_mock_response(updates)), \
         patch("httpx.post", return_value=_mock_response({"ok": True})) as mock_post:
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    new_cfg = yaml.safe_load(cfg.read_text())
    assert new_cfg["searches"][0]["text_must_contain"] == ["balkon", "taras"]
    assert new_cfg["searches"][0]["text_must_not_contain"] == ["kawalerka"]
    assert mock_post.call_count == 3
    assert json.loads(state.read_text())["last_update_id"] == 12


def test_poll_unknown_command_replies_with_help_hint(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": [_build_update(20, 555, "/foo bar")]}

    captured_text = {}

    def capture_post(url, **kwargs):
        captured_text["text"] = kwargs.get("json", {}).get("text", "")
        return _mock_response({"ok": True})

    with patch("httpx.get", return_value=_mock_response(updates)), \
         patch("httpx.post", side_effect=capture_post):
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    assert "unknown" in captured_text["text"].lower()
    assert "/help" in captured_text["text"]


def test_poll_uses_offset_from_state(tmp_path):
    cfg = _make_config_file(tmp_path)
    state = _make_state(tmp_path, last_update_id=42)
    seen = _make_seen(tmp_path)

    updates = {"ok": True, "result": []}

    captured_url = {}

    def capture_get(url, **kwargs):
        captured_url["url"] = url
        captured_url["params"] = kwargs.get("params", {})
        return _mock_response(updates)

    with patch("httpx.get", side_effect=capture_get):
        poll_and_process("TOK", chat_id=555, config_file=cfg, bot_state_file=state, seen_file=seen)

    assert captured_url["params"].get("offset") == 43
