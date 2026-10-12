"""Simulated sensors: plays hands by feeding the engine the same observed
events a real table would (cards read, blinds seen, bets seen, boards read).

The driver owns the deck. It never touches the rules: it asks the engine what
input it is waiting for (`awaiting` in the dealer snapshot) and answers it. So
the engine enforces order, legality, pot limits, side pots, and so on.

It can run two ways, through the same `Port` interface:

    LocalPort   inside the API process, calling the runtime directly
    RemotePort  as a separate process, over WebSockets, exactly as a real
                sensor bridge would:   python -m api.driver ws://localhost:8000
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from typing import Any, Protocol

NAMES = ["Maya", "Dan", "Priya", "Leo", "Sam", "Tim H", "Chris", "Ava"]
STACKS = [412, 188, 530, 95, 260, 740, 300, 720]
RANKS = "AKQJT98765432"


class Port(Protocol):
    async def snapshot(self) -> dict[str, Any]: ...
    async def send(self, event: dict) -> str | None: ...
    async def command(self, msg: dict) -> str | None: ...


class LocalPort:
    """Talks to the runtime in the same process."""

    def __init__(self, runtime) -> None:
        self.rt = runtime

    async def snapshot(self) -> dict:
        return self.rt.table.snapshot()

    async def send(self, event: dict) -> str | None:
        return self.rt.event(event)

    async def command(self, msg: dict) -> str | None:
        return self.rt.command(msg)


class RemotePort:
    """Talks to a running API over WebSockets: /ws/events to send observed
    events, /ws/dealer to read the table's state and send dealer commands."""

    def __init__(self, base: str, token: str = "") -> None:
        q = f"?token={token}" if token else ""
        self.events_url = f"{base}/ws/events{q}"
        self.dealer_url = f"{base}/ws/dealer{q}"
        self.state: dict | None = None
        self._events = None
        self._dealer = None
        self._reader: asyncio.Task | None = None

    async def connect(self) -> None:
        import websockets

        self._events = await websockets.connect(self.events_url)
        self._dealer = await websockets.connect(self.dealer_url)
        self._reader = asyncio.create_task(self._read_dealer())
        while self.state is None:
            await asyncio.sleep(0.05)

    async def _read_dealer(self) -> None:
        async for raw in self._dealer:
            msg = json.loads(raw)
            if msg["type"] == "state":
                self.state = msg["state"]

    async def snapshot(self) -> dict:
        return self.state or {}

    async def send(self, event: dict) -> str | None:
        await self._events.send(json.dumps(event))
        reply = json.loads(await self._events.recv())
        # State arrives on a different socket and can lag the reply. Wait until
        # we have seen the version this event produced, or we would act on
        # stale state and send the same thing twice.
        want = reply.get("version", 0)
        for _ in range(100):
            if self.state and self.state.get("version", 0) >= want:
                break
            await asyncio.sleep(0.02)
        return None if reply["ok"] else reply["error"]

    async def command(self, msg: dict) -> str | None:
        await self._dealer.send(json.dumps(msg))
        return None


class SensorDriver:
    def __init__(self, port: Port, speed: float = 1.0, seed_players: bool = True) -> None:
        self.port = port
        self.speed = speed
        self.seed_players = seed_players
        self._seeded = False
        self._hand = -1
        self._deck: list[str] = []
        self._dealt: dict[int, list[str]] = {}
        self._boards: list[list[str]] = []
        self._scenario = "normal"
        self._shovers: set[int] = set()
        self._raises: dict[str, int] = {}
        self._opened = False
        self.errors: list[str] = []

    async def _pause(self, seconds: float) -> None:
        if self.speed > 0:
            await asyncio.sleep(seconds * self.speed)
        else:
            await asyncio.sleep(0)

    async def _send(self, event: dict) -> None:
        error = await self.port.send(event)
        if error:
            self.errors.append(f"{event}: {error}")

    # ------------------------------------------------------------------

    async def run(self) -> None:
        while True:
            try:
                await self.step()
            except asyncio.CancelledError:
                raise
            except Exception as exc:               # keep the table alive
                self.errors.append(repr(exc))
                await asyncio.sleep(1)
            await self._pause(0.15)

    async def step(self) -> None:
        snap = await self.port.snapshot()
        if not snap:
            return
        phase = snap["phase"]

        if phase == "waiting":
            if self.seed_players and not self._seeded and not any(p["name"] for p in snap["players"]):
                self._seeded = True
                for i, (name, stack) in enumerate(zip(NAMES, STACKS), start=1):
                    await self.port.command({"cmd": "add_player", "seat": i, "name": name, "stack": stack})
                await self._pause(0.3)
                await self.port.command({"cmd": "deal_hand"})
            return

        if snap["hand"] != self._hand:
            self._new_hand(snap)

        awaiting = snap["awaiting"]
        kind = awaiting["kind"]

        if kind == "cards":
            seats = awaiting["seats"]
            if seats:
                seat = random.choice(seats)          # cards are read in no set order
                await self._send({"type": "cards", "seat": seat, "cards": self._dealt[seat]})
                await self._pause(0.45)
        elif kind == "blinds":
            if awaiting.get("blind"):
                b = awaiting["blind"]
                await self._send({"type": "blind", "seat": b["seat"], "amount": b["amount"]})
            elif awaiting.get("antes"):
                seat = awaiting["antes"][0]
                amount = next(min(snap["config"]["ante"], p["stack"]) for p in snap["players"] if p["seat"] == seat)
                await self._send({"type": "blind", "seat": seat, "amount": amount})
            await self._pause(0.5)
        elif kind == "action":
            await self._play(snap, awaiting["legal"])
        elif kind == "board":
            n = awaiting["cards"]
            await self._pause(0.8)
            await self._send({"type": "board", "boards": [b[:n] for b in self._boards]})
            await self._pause(1.6)
        # showdown / next_hand: the dealer presses those buttons

    # ------------------------------------------------------------------

    def _new_hand(self, snap: dict) -> None:
        self._hand = snap["hand"]
        n_hole = snap["holeCards"]
        deck = [r + s for r in RANKS for s in "shdc"]
        random.shuffle(deck)
        self._dealt = {seat: deck[i * n_hole:(i + 1) * n_hole] for i, seat in enumerate(snap["order"])}
        rest = deck[len(snap["order"]) * n_hole:]
        boards = snap["config"]["boards"]
        self._boards = [rest[i * 5:(i + 1) * 5] for i in range(boards)]
        self._raises = {}
        self._opened = False
        self._scenario = ["normal", "shove", "normal", "uncontested"][snap["hand"] % 4]
        if snap["config"]["bomb"] and self._scenario == "uncontested":
            self._scenario = "normal"
        self._shovers = set(random.sample(snap["order"], min(3, len(snap["order"]))))

    async def _play(self, snap: dict, legal: dict) -> None:
        seat = legal["seat"]
        street = snap["street"]
        bb = snap["config"]["bb"]
        to_call, can_check = legal["toCall"], legal["canCheck"]
        raises = self._raises.get(street, 0)

        def raise_to() -> int:
            size = legal["minRaiseTo"] + random.randint(0, 3) * bb
            return min(size, legal["maxRaiseTo"])

        action: tuple[str, int | None]
        if self._scenario == "uncontested" and street == "preflop":
            if not self._opened:
                self._opened = True
                action = ("raise", min(3 * bb, legal["maxRaiseTo"]))
            else:
                action = ("fold", None)
        elif self._scenario == "shove":
            if seat in self._shovers:
                # "all in" where that is legal; in a pot-limit game, the biggest raise allowed
                if legal["maxRaiseTo"] >= legal["allInTo"]:
                    action = ("all_in", None)
                elif legal["maxRaiseTo"] > legal["currentBet"]:
                    action = self._bet(legal, legal["maxRaiseTo"])
                else:
                    action = ("call", None) if not can_check else ("check", None)
            else:
                action = ("check", None) if can_check else ("fold", None)
        else:
            r = random.random()
            can_raise = legal["maxRaiseTo"] > legal["minRaiseTo"] or legal["maxRaiseTo"] > 0
            if can_check:
                action = ("check", None) if r < 0.65 or raises >= 2 else self._bet(legal, raise_to())
            elif r < 0.25:
                action = ("fold", None)
            elif r < 0.8 or raises >= 2 or not can_raise:
                action = ("call", None)
            else:
                action = self._bet(legal, raise_to())

        if action[0] in ("bet", "raise", "all_in"):
            self._raises[street] = raises + 1
        await self._pause(1.1)
        await self._send({"type": "action", "seat": seat, "action": action[0], "to": action[1]})

    @staticmethod
    def _bet(legal: dict, to: int) -> tuple[str, int | None]:
        if to >= legal["allInTo"]:
            return ("all_in", None)
        # "bet" opens the betting; once anyone has put chips in (even the blinds) it is a raise
        return ("bet" if legal["currentBet"] == 0 else "raise", to)


async def _main(url: str, token: str, speed: float) -> None:
    port = RemotePort(url, token)
    await port.connect()
    print(f"connected to {url}; playing as a sensor bridge")
    driver = SensorDriver(port, speed=speed, seed_players=False)
    await driver.run()


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "ws://localhost:8000"
    asyncio.run(_main(base, token="", speed=1.0))
