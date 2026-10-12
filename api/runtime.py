"""Connects the engine (sync, no I/O) to the network (async).

The engine reports changes through plain callbacks. This module turns them
into ordered WebSocket messages:

    engine on_state    -> latest snapshot, coalesced  -> every dealer UI
    engine on_overlay  -> events, strictly in order   -> every overlay
    engine on_equity   -> computed in a worker thread -> overlay "equity" event

It also maps incoming messages (dealer commands, sensor events) onto engine
methods. All engine calls happen on the event-loop thread, so the engine never
needs locks.
"""

from __future__ import annotations

import asyncio
from typing import Any

from engine import equity
from engine.table import Table

from . import storage
from .hub import Hub


class Runtime:
    def __init__(self) -> None:
        self.table = Table(summary_sink=storage.save_summary)
        self.hub = Hub()
        self._overlay_q: asyncio.Queue[dict] = asyncio.Queue()
        self._state_dirty = asyncio.Event()
        self._latest: dict | None = None
        self._eq_gen = 0
        self._tasks: list[asyncio.Task] = []

        self.table.on_overlay.append(self._overlay_q.put_nowait)
        self.table.on_state.append(self._on_state)
        self.table.on_equity.append(self._on_equity)

    # ----------------------------------------------------------- lifecycle

    def start(self) -> None:
        self._tasks = [
            asyncio.create_task(self._overlay_worker()),
            asyncio.create_task(self._state_worker()),
        ]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # ----------------------------------------------------------- outbound

    def _on_state(self, snapshot: dict) -> None:
        self._latest = snapshot
        self._state_dirty.set()

    async def _state_worker(self) -> None:
        """Send the newest snapshot. If several changes pile up, only the last
        one matters, so the UI is never sent stale state."""
        while True:
            await self._state_dirty.wait()
            self._state_dirty.clear()
            if self._latest is not None:
                await self.hub.publish(self._latest)

    async def _overlay_worker(self) -> None:
        """Overlay events are a script, so they must go out in order."""
        while True:
            event = await self._overlay_q.get()
            await self.hub.emit(event)

    def _on_equity(self, request: dict) -> None:
        self._eq_gen += 1
        asyncio.create_task(self._compute_equity(self._eq_gen, request))

    async def _compute_equity(self, gen: int, request: dict) -> None:
        variant = request["variant"]
        holes = {int(s): c for s, c in request["holes"].items()}
        boards = request["boards"] or [[]]
        samples = 500 if variant == "nlh" else 250

        def work() -> tuple[dict[int, float], dict[int, list[str]]]:
            per_board = [equity.equities(variant, holes, b, samples) for b in boards]
            eq = {s: sum(e[s] for e in per_board) / len(per_board) for s in holes}
            hints = equity.outs(variant, holes, boards[0]) if len(boards) == 1 else {}
            return eq, hints

        eq, hints = await asyncio.to_thread(work)          # CPU work off the event loop
        table = self.table
        if gen != self._eq_gen or request["hand"] != table.hand or table.phase in ("waiting", "showdown"):
            return                                          # something newer has happened
        self._overlay_q.put_nowait({
            "type": "equity",
            "equities": {str(s): round(v, 1) for s, v in eq.items()},
            "outs": {str(s): cards for s, cards in hints.items()},
        })

    # ------------------------------------------------------------ inbound

    def command(self, msg: dict) -> str | None:
        """Dealer UI commands."""
        t = self.table
        cmd = msg.get("cmd")
        seat = msg.get("seat")
        match cmd:
            case "deal_hand":
                return t.deal_hand()
            case "showdown":
                return t.showdown()
            case "next_hand":
                return t.next_hand()
            case "set_config":
                return t.set_config(msg.get("config") or {})
            case "edit_name":
                return t.edit_name(seat, msg.get("name", ""))
            case "adjust_stack":
                return t.adjust_stack(seat, msg.get("amount"))
            case "remove_player":
                return t.remove_player(seat)
            case "add_player":
                return t.add_player(seat, msg.get("name", ""), msg.get("stack"))
            case "seat_returning":
                return t.seat_returning(seat, msg.get("id"), msg.get("stack"))
            case "new_game":
                return t.new_game()
        return f"Unknown command {cmd!r}."

    def event(self, msg: dict) -> str | None:
        """Observed events from sensors (RFID readers, a camera, a test tool)."""
        t = self.table
        kind = msg.get("type")
        match kind:
            case "cards":
                return t.register_cards(msg.get("seat"), msg.get("cards") or [])
            case "blind":
                return t.post_blind(msg.get("seat"), msg.get("amount"))
            case "action":
                return t.act(msg.get("seat"), msg.get("action", ""), msg.get("to"))
            case "board":
                return t.register_board(msg.get("boards") or [])
        return f"Unknown event type {kind!r}."
