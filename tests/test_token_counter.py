from utils.token_counter import estimate_tokens, estimate_messages_tokens, context_usage_percent, context_status


def test_estimate_tokens_empty_and_nonempty():
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") >= 1


def test_estimate_messages_tokens_includes_overhead():
    msgs = [{"content": "hello"}, {"content": "world"}]
    base = estimate_tokens("hello") + estimate_tokens("world")
    assert estimate_messages_tokens(msgs) == base + 8


def test_context_status_thresholds():
    assert context_status(10, 1000) == "ok"
    assert context_status(600, 1000) == "moderate"
    assert context_status(800, 1000) == "warning"
    assert context_status(950, 1000) == "critical"
    assert context_usage_percent(2000, 1000) == 100.0
