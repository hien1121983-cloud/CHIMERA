"""Smoke tests cho 4 hàm Mongo mới + send_long_message.

Yêu cầu: mongomock (đã thêm vào requirements.txt).
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import mongomock
import pytest


@pytest.fixture
def mock_mongo(monkeypatch):
    """Patch _client() để trả về mongomock client cho cả 3 cụm."""
    from src.storage import mongo as m
    clients = {i: mongomock.MongoClient() for i in (1, 2, 3)}
    monkeypatch.setattr(m, "_client", lambda idx: clients[idx])
    # reset gridfs cache nếu có
    if hasattr(m._gridfs_scripts, "cache_clear"):
        m._gridfs_scripts.cache_clear()
    return clients


def test_set_and_find_episode_state(mock_mongo):
    from src.storage import mongo as m
    m.set_episode_state("ep_001", "awaiting_scene1", {"foo": "bar"})
    doc = m.find_episode_in_state("awaiting_scene1")
    assert doc is not None
    assert doc["episode_id"] == "ep_001"
    assert doc["state"] == "awaiting_scene1"
    assert doc.get("foo") == "bar"


def test_find_episode_in_state_empty(mock_mongo):
    from src.storage import mongo as m
    assert m.find_episode_in_state("nonexistent_state") is None


def test_set_episode_state_updates_existing(mock_mongo):
    from src.storage import mongo as m
    m.set_episode_state("ep_002", "state_a")
    m.set_episode_state("ep_002", "state_b")
    assert m.find_episode_in_state("state_a") is None
    doc = m.find_episode_in_state("state_b")
    assert doc and doc["episode_id"] == "ep_002"


def test_send_long_message_splits(monkeypatch):
    from src.delivery import telegram_bot as tb
    sent = []
    monkeypatch.setattr(tb, "send_message", lambda text, **kw: sent.append(text))
    long_text = "A" * 3800 + "\n\n" + "B" * 3800
    tb.send_long_message(long_text)
    assert len(sent) >= 2
    assert all(len(chunk) <= 4000 for chunk in sent)
    assert "".join(sent).count("A") == 3800
    assert "".join(sent).count("B") == 3800


def test_send_long_message_short(monkeypatch):
    from src.delivery import telegram_bot as tb
    sent = []
    monkeypatch.setattr(tb, "send_message", lambda text, **kw: sent.append(text))
    tb.send_long_message("short message")
    assert sent == ["short message"]
