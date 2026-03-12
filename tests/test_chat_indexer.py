from utils.chat_indexer import ChatIndexer


def test_search_prefers_recent_chat_mtime_when_limited():
    idx = ChatIndexer()
    idx._index = {
        '/tmp/old.jsonl': [(0, 'user', 'alpha hit', '2024-01-01T00:00:00')],
        '/tmp/new.jsonl': [(0, 'user', 'alpha hit', '2024-01-02T00:00:00')],
    }
    idx._mtimes = {
        '/tmp/old.jsonl': 100.0,
        '/tmp/new.jsonl': 200.0,
    }

    results = idx.search('alpha', max_results=1)
    assert len(results) == 1
    assert str(results[0].chat_path) == '/tmp/new.jsonl'


def test_search_returns_recent_message_first_within_chat():
    idx = ChatIndexer()
    idx._index = {
        '/tmp/chat.jsonl': [
            (0, 'user', 'beta here', '2024-01-01T00:00:00'),
            (1, 'assistant', 'beta again', '2024-01-02T00:00:00'),
        ]
    }
    idx._mtimes = {'/tmp/chat.jsonl': 123.0}

    results = idx.search('beta', max_results=2)
    assert len(results) == 2
    assert results[0].timestamp >= results[1].timestamp
