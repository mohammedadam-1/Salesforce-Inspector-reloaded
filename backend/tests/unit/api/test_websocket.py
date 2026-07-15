import uuid
import json
from unittest.mock import AsyncMock, patch

import pytest

from sfir_backend.api.websocket import WebSocketConnection, WebSocketManager


class TestWebSocketConnection:
    def test_create(self) -> None:
        ws = AsyncMock()
        user_id = uuid.uuid4()
        conn = WebSocketConnection(ws, user_id)
        assert conn.user_id == user_id
        assert conn.connection_id is not None
        assert not conn._closed

    async def test_send_json(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        await conn.send_json({"test": "data"})
        ws.send_json.assert_called_with({"test": "data"})

    async def test_send_json_when_closed(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        conn._closed = True
        await conn.send_json({"test": "data"})
        ws.send_json.assert_not_called()

    async def test_send_message(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        await conn.send_message("channel1", "event1", {"key": "value"})
        ws.send_json.assert_called_once()
        args = ws.send_json.call_args[0][0]
        assert args["channel"] == "channel1"
        assert args["event"] == "event1"

    async def test_close(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        await conn.close()
        ws.close.assert_called()


class TestWebSocketManager:
    def setup_method(self) -> None:
        self.manager = WebSocketManager()

    def test_connection_count_empty(self) -> None:
        assert self.manager.connection_count() == 0

    def test_channel_subscriber_count(self) -> None:
        assert self.manager.channel_subscriber_count("test") == 0

    async def test_register_and_count(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        self.manager._connections[conn.connection_id] = conn
        assert self.manager.connection_count() == 1
        self.manager._remove_connection(conn)
        assert self.manager.connection_count() == 0

    async def test_subscribe_channel(self) -> None:
        ws = AsyncMock()
        conn = WebSocketConnection(ws, uuid.uuid4())
        conn.subscribed_channels.add("alerts")
        self.manager._connections[conn.connection_id] = conn
        self.manager._channels.setdefault("alerts", set()).add(conn.connection_id)
        assert conn.connection_id in self.manager._channels["alerts"]

    async def test_broadcast_to_channel(self) -> None:
        ws = AsyncMock()
        user_id = uuid.uuid4()
        conn = WebSocketConnection(ws, user_id)
        conn.subscribed_channels.add("alerts")
        self.manager._connections[conn.connection_id] = conn
        self.manager._channels.setdefault("alerts", set()).add(conn.connection_id)

        sent = await self.manager.broadcast("alerts", "test-event", {"msg": "hello"})
        assert sent == 1
        ws.send_json.assert_called_once()

    async def test_broadcast_to_empty_channel(self) -> None:
        sent = await self.manager.broadcast("nonexistent", "evt", {})
        assert sent == 0

    async def test_broadcast_all(self) -> None:
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        id1 = uuid.uuid4()
        id2 = uuid.uuid4()
        self.manager._connections[id1] = WebSocketConnection(ws1, uuid.uuid4())
        self.manager._connections[id2] = WebSocketConnection(ws2, uuid.uuid4())

        sent = await self.manager.broadcast_all("system", {"msg": "broadcast"})
        assert sent == 2
