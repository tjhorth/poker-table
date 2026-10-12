"""Connections to the dealer UI and the stream overlay."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import WebSocket


class Hub:
    def __init__(self) -> None:
        self.dealers: set[WebSocket] = set()
        self.overlays: set[WebSocket] = set()
        self._log: list[dict[str, Any]] = []   # overlay events for the current hand

    # -- dealer UI: full state snapshots -------------------------------------

    async def connect_dealer(self, ws: WebSocket, snapshot: dict) -> None:
        await ws.accept()
        self.dealers.add(ws)
        await ws.send_json({"type": "state", "state": snapshot})

    async def publish(self, snapshot: dict) -> None:
        await self._fan_out(self.dealers, {"type": "state", "state": snapshot})

    # -- overlay: an event stream ---------------------------------------------

    async def connect_overlay(self, ws: WebSocket) -> None:
        await ws.accept()
        self.overlays.add(ws)
        if self._log:                       # catch a late joiner up on this hand
            await ws.send_json(self._log)

    async def emit(self, event: dict) -> None:
        if event["type"] == "hand_start":
            self._log = []
        self._log.append(event)
        await self._fan_out(self.overlays, event)

    # ------------------------------------------------------------------------

    @staticmethod
    async def _fan_out(sockets: set[WebSocket], message: Any) -> None:
        async def send(ws: WebSocket) -> None:
            try:
                await ws.send_json(message)
            except Exception:
                sockets.discard(ws)

        await asyncio.gather(*(send(ws) for ws in list(sockets)))
