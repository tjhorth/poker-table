"""Dealer + overlay API.

    pipenv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

  /ws/dealer    state snapshots out, commands in  (dealer UI)
  /ws/overlay   overlay events out                (stream overlay)
  /overlay/     the overlay page itself, for convenience
"""

from __future__ import annotations

import asyncio
import json
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .hub import Hub
from .sim import GAMES_DIR, TableSim

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


@app.get("/api/games")
async def recent_games(limit: int = 3) -> list[dict]:
    """Summaries of the most recent saved games, newest first."""
    limit = max(1, min(limit, 50))
    files = sorted(GAMES_DIR.glob("game-*.json"), reverse=True)[:limit] if GAMES_DIR.is_dir() else []
    games = []
    for f in files:
        try:
            games.append({"id": f.stem, **json.loads(f.read_text())})
        except (OSError, ValueError):
            continue                      # skip a file that is unreadable or half written
    return games


@app.get("/api/games/{game_id}.csv")
async def game_csv(game_id: str) -> FileResponse:
    if not re.fullmatch(r"game-\d{8}-\d{6}", game_id):
        raise HTTPException(404)
    path = GAMES_DIR / f"{game_id}.csv"
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type="text/csv", filename=f"{game_id}.csv")


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
