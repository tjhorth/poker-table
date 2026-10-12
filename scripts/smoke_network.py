#!/usr/bin/env python3
"""Checks that the API works end to end over real WebSockets.

    # terminal 1: the API with its built-in simulator off
    POKER_SIM=0 python -m api
    # terminal 2:
    python scripts/smoke_network.py ws://localhost:8000

Point it at ws://<server-ip>:8000 to test the network path from another
machine. It plays as three separate clients, like the real system:

    dealer   /ws/dealer    sees state, presses Deal / Showdown / Next Hand
    overlay  /ws/overlay   receives the event script for the stream
    sensor   /ws/events    sends observed cards, blinds, bets, boards
"""

import asyncio
import json
import sys
import time

import websockets

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0])
from api.driver import RemotePort, SensorDriver  # noqa: E402


async def main(base: str, token: str) -> int:
    q = f"?token={token}" if token else ""
    started = time.perf_counter()

    dealer = await websockets.connect(f"{base}/ws/dealer{q}")
    overlay = await websockets.connect(f"{base}/ws/overlay{q}")
    print(f"connected dealer + overlay in {1000 * (time.perf_counter() - started):.0f} ms")

    overlay_events: list[dict] = []

    async def read_overlay() -> None:
        async for raw in overlay:
            data = json.loads(raw)
            overlay_events.extend(data if isinstance(data, list) else [data])

    state: dict = {}
    errors: list[str] = []

    async def read_dealer() -> None:
        async for raw in dealer:
            msg = json.loads(raw)
            if msg["type"] == "state":
                state.update(msg["state"])
            else:
                errors.append(msg["message"])

    readers = [asyncio.create_task(read_overlay()), asyncio.create_task(read_dealer())]

    async def command(msg: dict) -> None:
        await dealer.send(json.dumps(msg))

    async def wait(pred, what: str, timeout: float = 60) -> None:
        end = time.monotonic() + timeout
        while not pred():
            if time.monotonic() > end:
                raise SystemExit(f"timed out waiting for {what}; phase={state.get('phase')} errors={errors}")
            await asyncio.sleep(0.05)

    await wait(lambda: state, "the first snapshot")
    if state["phase"] == "waiting":
        for seat, (name, stack) in enumerate([("Ann", 300), ("Bob", 300), ("Cy", 300), ("Di", 300)], 1):
            if not state["players"][seat - 1]["name"]:
                await command({"cmd": "add_player", "seat": seat, "name": name, "stack": stack})
        await wait(lambda: state["canDeal"], "enough players")
        await command({"cmd": "deal_hand"})

    port = RemotePort(base, token)
    await port.connect()
    driver = SensorDriver(port, speed=0.0, seed_players=False)
    sensor = asyncio.create_task(driver.run())

    hands = 0
    for _ in range(3):
        await wait(lambda: state["canShowdown"], "the hand to reach showdown")
        await command({"cmd": "showdown"})
        await wait(lambda: state["canNextHand"], "the showdown result")
        r = state["showdown"]
        paid = sum(p["won"] for p in r["players"])
        pots = sum(p["amount"] for p in r["pots"])
        print(f"hand {state['hand']}: {state['gameLabel']}, pots {pots}, paid out {paid}, "
              f"winners {[p['name'] for p in r['players'] if p['won'] > 0]}")
        assert paid == pots, "payouts do not match the pots"
        hands += 1
        await command({"cmd": "next_hand"})
        await wait(lambda: state["phase"] in ("dealing", "blinds", "betting"), "the next hand")

    sensor.cancel()
    await asyncio.sleep(0.2)
    kinds: dict[str, int] = {}
    for e in overlay_events:
        kinds[e["type"]] = kinds.get(e["type"], 0) + 1
    print("overlay events received:", kinds)
    print("sensor errors:", driver.errors or "none")
    print("dealer errors:", errors or "none")
    for r in readers:
        r.cancel()
    ok = not driver.errors and not errors and hands == 3 and kinds.get("hand_start", 0) >= 3
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000"
    tok = sys.argv[2] if len(sys.argv) > 2 else ""
    raise SystemExit(asyncio.run(main(url, tok)))
