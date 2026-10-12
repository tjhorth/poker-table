"""The network face of the table.

    python -m api                      # runs this app with api/config.py settings

  WS   /ws/dealer    dealer UI: snapshots out, commands in
  WS   /ws/overlay   stream overlay: ordered events out
  WS   /ws/events    sensors / test tools: observed events in, replies out
  GET  /api/state    the current dealer snapshot (handy for debugging)
  GET  /api/games    saved game summaries, newest first
  GET  /api/games/<id>.csv
  GET  /health
  GET  /overlay/     the overlay page, served for convenience
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import storage
from .config import REPO, settings
from .driver import LocalPort, SensorDriver
from .runtime import Runtime

runtime = Runtime()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    runtime.start()
    driver_task = None
    if settings.sim:
        driver = SensorDriver(LocalPort(runtime), speed=settings.sim_speed,
                              seed_players=settings.sim_seed_players)
        driver_task = asyncio.create_task(driver.run())
    yield
    if driver_task:
        driver_task.cancel()
    await runtime.stop()


app = FastAPI(title="Poker table", lifespan=lifespan)

# Browsers enforce CORS on fetch/XHR calls to another origin (another host or
# port). WebSockets are not covered by CORS, so they get their own Origin check.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


def _origin_ok(origin: str | None) -> bool:
    if "*" in settings.allowed_origins or origin is None:
        return True                      # non-browser clients send no Origin
    return origin in settings.allowed_origins


def _token_ok(token: str | None) -> bool:
    return not settings.token or token == settings.token


async def _guard(ws: WebSocket, token: str | None) -> bool:
    """Reject the WebSocket handshake before it is accepted (HTTP 403)."""
    if not _origin_ok(ws.headers.get("origin")) or not _token_ok(token):
        await ws.close(code=1008)
        return False
    return True


def _require_token(token: str | None) -> None:
    if not _token_ok(token):
        raise HTTPException(401, "A valid ?token= is required.")


@app.get("/health")
async def health() -> dict:
    t = runtime.table
    return {"ok": True, "hand": t.hand, "phase": t.phase,
            "dealers": len(runtime.hub.dealers), "overlays": len(runtime.hub.overlays)}


@app.get("/api/state")
async def state(token: str | None = Query(None)) -> dict:
    _require_token(token)
    return runtime.table.snapshot()


@app.get("/api/games")
async def games(limit: int = 3, token: str | None = Query(None)) -> list[dict]:
    _require_token(token)
    return storage.recent_games(max(1, min(limit, 50)))


@app.get("/api/games/{game_id}.csv")
async def game_csv(game_id: str, request: Request, token: str | None = Query(None)) -> FileResponse:
    _require_token(token)
    path = storage.csv_path(game_id)
    if path is None:
        raise HTTPException(404)
    return FileResponse(path, media_type="text/csv", filename=f"{game_id}.csv")


@app.websocket("/ws/dealer")
async def ws_dealer(ws: WebSocket, token: str | None = Query(None)) -> None:
    if not await _guard(ws, token):
        return
    await runtime.hub.connect_dealer(ws, runtime.table.snapshot())
    try:
        while True:
            message = await ws.receive_json()
            error = runtime.command(message)
            if error:
                await ws.send_json({"type": "error", "message": error})
    except WebSocketDisconnect:
        pass
    finally:
        runtime.hub.dealers.discard(ws)


@app.websocket("/ws/overlay")
async def ws_overlay(ws: WebSocket, token: str | None = Query(None)) -> None:
    if not await _guard(ws, token):
        return
    await runtime.hub.connect_overlay(ws)
    try:
        while True:
            await ws.receive_text()      # nothing is expected; this notices disconnects
    except WebSocketDisconnect:
        pass
    finally:
        runtime.hub.overlays.discard(ws)


@app.websocket("/ws/events")
async def ws_events(ws: WebSocket, token: str | None = Query(None)) -> None:
    """Sensors send observed events; every one gets an {"ok": ...} reply."""
    if not await _guard(ws, token):
        return
    await ws.accept()
    try:
        while True:
            message = await ws.receive_json()
            error = runtime.event(message)
            # "version" is the table state version after this event, so a sensor
            # can wait for the dealer-state push that reflects it
            await ws.send_json({
                "ok": error is None,
                "version": runtime.table.version,
                **({"error": error} if error else {}),
            })
    except WebSocketDisconnect:
        pass


_overlay = REPO / "web" / "overlay"
if _overlay.is_dir():
    app.mount("/overlay", StaticFiles(directory=_overlay, html=True), name="overlay")
