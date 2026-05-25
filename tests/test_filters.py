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
