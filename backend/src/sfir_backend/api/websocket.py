from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL = 30
HEARTBEAT_TIMEOUT = 10


class WebSocketConnection:
    def __init__(self, websocket: WebSocket, user_id: uuid.UUID) -> None:
        self.websocket = websocket
        self.user_id = user_id
        self.connection_id = uuid.uuid4()
        self.subscribed_channels: set[str] = set()
        self._closed = False

    async def send_json(self, data: dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            await self.websocket.send_json(data)
        except Exception:
            self._closed = True

    async def send_message(
        self,
        channel: str,
        event: str,
        data: dict[str, Any],
    ) -> None:
        await self.send_json({
            "channel": channel,
            "event": event,
            "data": data,
            "connection_id": str(self.connection_id),
        })

    async def close(self, code: int = 1000) -> None:
        self._closed = True
        try:
            if self.websocket.client_state != WebSocketState.DISCONNECTED:
                await self.websocket.close(code=code)
        except Exception:
            pass


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, WebSocketConnection] = {}
        self._channels: dict[str, set[uuid.UUID]] = {}

    async def handle_connection(
        self,
        websocket: WebSocket,
        user_id: uuid.UUID,
    ) -> None:
        await websocket.accept()
        connection = WebSocketConnection(websocket, user_id)
        self._connections[connection.connection_id] = connection
        logger.info(
            "websocket_connected",
            connection_id=str(connection.connection_id),
            user_id=str(user_id),
        )

        heartbeat_task = asyncio.create_task(self._heartbeat(connection))

        try:
            await self._handle_messages(connection)
        except WebSocketDisconnect:
            pass
        finally:
            heartbeat_task.cancel()
            self._remove_connection(connection)

    async def _handle_messages(self, connection: WebSocketConnection) -> None:
        async for message in connection.websocket.iter_text():
            try:
                data = json.loads(message)
                msg_type = data.get("type", "")
                if msg_type == "subscribe":
                    channel = data.get("channel", "")
                    if channel:
                        connection.subscribed_channels.add(channel)
                        self._channels.setdefault(channel, set()).add(connection.connection_id)
                        await connection.send_message("system", "subscribed", {"channel": channel})
                elif msg_type == "unsubscribe":
                    channel = data.get("channel", "")
                    connection.subscribed_channels.discard(channel)
                    self._channels.get(channel, set()).discard(connection.connection_id)
                    await connection.send_message("system", "unsubscribed", {"channel": channel})
                elif msg_type == "pong":
                    pass
            except json.JSONDecodeError:
                await connection.send_message("system", "error", {"message": "Invalid JSON"})

    async def _heartbeat(self, connection: WebSocketConnection) -> None:
        while True:
            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if connection._closed:
                    break
                await connection.send_json({"type": "ping"})
            except Exception:
                break

    def _remove_connection(self, connection: WebSocketConnection) -> None:
        self._connections.pop(connection.connection_id, None)
        for channel in connection.subscribed_channels:
            self._channels.get(channel, set()).discard(connection.connection_id)
        logger.info("websocket_disconnected", connection_id=str(connection.connection_id))

    async def broadcast(
        self,
        channel: str,
        event: str,
        data: dict[str, Any],
    ) -> int:
        sent = 0
        conn_ids = self._channels.get(channel, set()).copy()
        for conn_id in conn_ids:
            conn = self._connections.get(conn_id)
            if conn and not conn._closed:
                await conn.send_message(channel, event, data)
                sent += 1
        return sent

    async def broadcast_all(self, event: str, data: dict[str, Any]) -> int:
        sent = 0
        for conn in list(self._connections.values()):
            if not conn._closed:
                await conn.send_message("broadcast", event, data)
                sent += 1
        return sent

    def connection_count(self) -> int:
        return len(self._connections)

    def channel_subscriber_count(self, channel: str) -> int:
        return len(self._channels.get(channel, set()))


async def authenticate_websocket(
    websocket: WebSocket,
    container: Any,
) -> uuid.UUID | None:
    token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        jwt_service = container.get_service("jwt")
        payload = jwt_service.decode_access_token(token)
        return uuid.UUID(payload["sub"])
    except (ValueError, KeyError):
        return None


_ws_manager = WebSocketManager()


def get_ws_manager() -> WebSocketManager:
    return _ws_manager
