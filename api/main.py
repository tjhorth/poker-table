"""Dealer + overlay API.

    pipenv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

  /ws/dealer    state snapshots out, commands in  (dealer UI)
  /ws/overlay   overlay events out                (stream overlay)
  /overlay/     the overlay page itself, for convenience
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from .hub import Hub
from .sim import TableSim

hub = Hub()
sim = TableSim(hub)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    task = asyncio.create_task(sim.run())
    yield
    task.cancel()


app = FastAPI(title="Poker table", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "hand": sim.hand, "phase": sim.phase}


@app.websocket("/ws/dealer")
async def ws_dealer(ws: WebSocket) -> None:
    await hub.connect_dealer(ws, sim.snapshot())
    try:
        while True:
            message = await ws.receive_json()
            error = await sim.command(message)
            if error:
                await ws.send_json({"type": "error", "message": error})
    except WebSocketDisconnect:
        pass
    finally:
        hub.dealers.discard(ws)


@app.websocket("/ws/overlay")
async def ws_overlay(ws: WebSocket) -> None:
    await hub.connect_overlay(ws)
    try:
        while True:
            await ws.receive_text()      # nothing expected; this notices disconnects
    except WebSocketDisconnect:
        pass
    finally:
        hub.overlays.discard(ws)


_overlay = Path(__file__).resolve().parents[1] / "web" / "overlay"
if _overlay.is_dir():
    app.mount("/overlay", StaticFiles(directory=_overlay, html=True), name="overlay")
