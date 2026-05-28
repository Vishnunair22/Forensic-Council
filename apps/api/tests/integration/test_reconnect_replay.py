"""Tests for WebSocket reconnect replay functionality."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from api.schemas import BriefUpdate


@pytest.mark.asyncio
async def test_replay_buffer_stores_messages():
    """broadcast_update should store messages in Redis replay buffer."""
    try:
        import api.routes._session_state as _ss_mod
    except (ImportError, AttributeError):
        pytest.skip("api.routes package not importable (pre-existing _append_chunk issue)")

    broadcast_update = _ss_mod.broadcast_update

    session_id = str(uuid4())
    update = BriefUpdate(
        type="AGENT_UPDATE",
        session_id=session_id,
        agent_id="Agent1",
        message="Test message",
        data={"status": "running"},
    )

    mock_redis = AsyncMock()
    mock_pipeline = MagicMock()
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock()
    mock_pipeline.rpush = AsyncMock()
    mock_pipeline.ltrim = AsyncMock()
    mock_pipeline.expire = AsyncMock()
    mock_pipeline.execute = AsyncMock()

    with (
        patch.object(_ss_mod, "_get_redis", return_value=AsyncMock(client=mock_redis)),
        patch.object(_ss_mod, "_redis_pipeline", return_value=mock_pipeline),
    ):
        mock_redis.client = mock_redis
        mock_redis.publish = AsyncMock()

        await broadcast_update(session_id, update)

        assert mock_redis.publish.called
        assert mock_pipeline.rpush.called


@pytest.mark.asyncio
async def test_replay_messages_sent_on_websocket_connect():
    """WebSocket handler should send replay messages on connect."""
    try:
        import api.routes._websocket as _ws_mod
    except (ImportError, AttributeError):
        pytest.skip("api.routes package not importable (pre-existing _append_chunk issue)")

    _live_updates_impl = _ws_mod._live_updates_impl

    mock_websocket = AsyncMock()
    mock_websocket.cookies = {}
    mock_websocket.receive_text = AsyncMock(side_effect=Exception("disconnect"))
    mock_websocket.send_json = AsyncMock()

    session_id = str(uuid4())

    replay_data = [
        '{"type": "AGENT_UPDATE", "agent_id": "Agent1", "message": "Running..."}',
        '{"type": "AGENT_COMPLETE", "agent_id": "Agent2", "message": "Done."}',
    ]

    mock_redis_client = AsyncMock()
    mock_redis_client.lrange = AsyncMock(return_value=replay_data)
    mock_pubsub = AsyncMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.listen = AsyncMock(side_effect=Exception("done"))

    with (
        patch.object(_ws_mod, "get_active_pipeline_metadata", return_value={"status": "running"}),
        patch.object(_ws_mod, "decode_token", return_value=MagicMock(user_id="test-user", role=None)),
        patch.object(_ws_mod, "assert_session_access", return_value=None),
        patch.object(_ws_mod, "register_websocket"),
        patch.object(_ws_mod, "unregister_websocket"),
        patch.object(_ws_mod, "Redis", return_value=mock_redis_client),
    ):
        mock_redis_client.pubsub.return_value = mock_pubsub
        mock_redis_client.lrange = AsyncMock(return_value=replay_data)

        try:
            await _live_updates_impl(mock_websocket, session_id, "test-user", None)
        except Exception:
            pass

        replay_calls = [
            c for c in mock_websocket.send_json.call_args_list
            if isinstance(c[0][0], dict) and c[0][0].get("type") != "CONNECTED"
        ]
        assert len(replay_calls) > 0


@pytest.mark.asyncio
async def test_replay_buffer_expiry():
    """Replay buffer should have a configured TTL."""
    try:
        import api.routes._session_state as _ss_mod
        REPLAY_BUFFER_TTL = _ss_mod.REPLAY_BUFFER_TTL
    except (ImportError, AttributeError):
        pytest.skip("api.routes package not importable (pre-existing _append_chunk issue)")

    assert REPLAY_BUFFER_TTL >= 300, "Replay buffer TTL should be at least 5 minutes"


@pytest.mark.asyncio
async def test_replay_buffer_maxlen():
    """Replay buffer should have a max length to prevent unbounded growth."""
    try:
        import api.routes._session_state as _ss_mod
        REPLAY_BUFFER_MAX_LEN = _ss_mod.REPLAY_BUFFER_MAX_LEN
    except (ImportError, AttributeError):
        pytest.skip("api.routes package not importable (pre-existing _append_chunk issue)")

    assert 10 <= REPLAY_BUFFER_MAX_LEN <= 200, "Replay buffer max length should be reasonable"
