from utils.session_state import _default_state


def test_default_state_contains_extended_restore_keys():
    state = _default_state()
    for key in [
        "splitter_sizes",
        "chat_scroll_positions",
        "timeline_visible",
        "suggestions_visible",
        "lan_checked",
        "input_draft",
        "active_model_topic",
    ]:
        assert key in state


from utils.session_state import _sanitize_state


def test_sanitize_state_repairs_invalid_types():
    repaired = _sanitize_state({
        "chat_scroll_positions": [],
        "splitter_sizes": "bad",
        "timeline_visible": "yes",
        "suggestions_visible": 0,
        "lan_checked": 1,
        "input_draft": 12,
        "active_model_topic": 9,
        "active_profile": 123,
    })

    assert isinstance(repaired["chat_scroll_positions"], dict)
    assert repaired["splitter_sizes"] == [240, 960, 0, 0]
    assert repaired["timeline_visible"] is True
    assert repaired["suggestions_visible"] is False
    assert repaired["lan_checked"] is True
    assert repaired["input_draft"] == ""
    assert repaired["active_model_topic"] is None
    assert repaired["active_profile"] == "Default"
