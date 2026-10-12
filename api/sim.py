"""A simulated table: plays scripted hands so the dealer UI and the overlay
have something live to show.

This stands in for the real game engine. It keeps the same contract the real
engine will have:

  * state snapshots for the dealer UI   (see TableSim.snapshot)
  * an event stream for the overlay     (hand_start, cards, blind, turn, ...)
  * commands from the dealer UI         (showdown, next_hand, set_config, ...)

Showdown results use PokerKit's hand evaluation.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import random
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pokerkit import Card, OmahaHoldemHand, StandardHighHand

from . import equity
from .hub import Hub

SEATS = list(range(1, 9))
NAMES = ["Maya", "Dan", "Priya", "Leo", "Sam", "Tim H", "Chris", "Ava"]
STACKS = [412, 188, 530, 95, 260, 740, 300, 720]
AUTO_REBUY = 200            # a player who is felted is topped up to this
MIN_PLAYERS = 3
VARIANTS = {"nlh": "NLH", "plo4": "PLO 4-card"}
BLIND_PRESETS = ["1/2", "2/5", "5/10", "10/20", "25/50"]
DEFAULT_CONFIG = {"variant": "nlh", "boards": 1, "bomb": False, "ante": 5, "sb": 1, "bb": 2}
CARD_ORDER = "AKQJT98765432"
SPEED = float(os.environ.get("SIM_SPEED", "1"))   # lower = faster simulated play
GAMES_DIR = Path(os.environ.get("POKER_GAMES_DIR", Path(__file__).resolve().parents[1] / "engine" / "data" / "games"))


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds * SPEED)


def game_label(cfg: dict) -> str:
    """NLH, PLO 4-card, 2brd NLH, Bomb Pot - PLO, Bomb Pot - 2brd PLO, ..."""
    if not cfg["bomb"] and cfg["boards"] == 1:
        return VARIANTS[cfg["variant"]]
    base = "NLH" if cfg["variant"] == "nlh" else "PLO"
    parts = []
    if cfg["bomb"]:
        parts.append("Bomb Pot -")
    if cfg["boards"] == 2:
        parts.append("2brd")
    return " ".join(parts + [base])


def hole_cards(cfg: dict) -> int:
    return 2 if cfg["variant"] == "nlh" else 4


class TableSim:
    def __init__(self, hub: Hub) -> None:
        self.hub = hub
        self.version = 0
        self.hand = 0
        self.button = 8
        self.config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.pending: dict[str, Any] | None = None
        self.note: str | None = None
        self._showdown = asyncio.Event()
        self._next = asyncio.Event()
        self._eq_gen = 0

        # seats persist from hand to hand
        self.names: dict[int, str | None] = {s: NAMES[s - 1] for s in SEATS}
        self.stack = {s: STACKS[s - 1] for s in SEATS}
        self.buy_in = {s: STACKS[s - 1] for s in SEATS}
        self.cashed_out = {s: 0 for s in SEATS}
        self.hands = {s: 0 for s in SEATS}          # hands each seated player was dealt into
        # players who left the table: their ledger is kept, with no seat
        self.inactive: list[dict[str, Any]] = []
        self._next_id = 1

        # the game as a whole
        self.game_started = datetime.now()
        self.game_hands = 0                          # completed hands
        self.last_summary: dict[str, Any] | None = None
        self._abort_for_new_game = False

        self._reset()
        self.phase = "waiting"

    # ---------------------------------------------------------------- state

    def _reset(self) -> None:
        self.phase = "dealing"
        self.street = "preflop"
        self.to_act: int | None = None
        self.order: list[int] = []
        self.contrib = {s: 0 for s in SEATS}
        self.in_street: dict[int, int] = {}
        self.folded: set[int] = set()
        self.all_in: set[int] = set()
        self.last_action: dict[int, str] = {}
        self.dealt: dict[int, list[str]] = {}
        self.registered: set[int] = set()
        self.boards: list[list[str]] = [[]]
        self.revealed = 0
        self.result: dict | None = None
        self.pots_final: list[dict] | None = None

    def seated(self) -> list[int]:
        return [s for s in SEATS if self.names[s] is not None]

    @property
    def blinds(self) -> str:
        return f"{self.config['sb']}/{self.config['bb']}"

    def pots_now(self) -> list[dict]:
        """Main pot plus side pots; a new pot starts above each all-in level."""
        live = [s for s in self.order if s not in self.folded]
        caps = sorted({self.contrib[s] for s in live if s in self.all_in and self.contrib[s] > 0})
        top = max([0] + [self.contrib[s] for s in live])
        if not caps or caps[-1] < top:
            caps.append(top)
        pots, prev = [], 0
        for cap in caps:
            amount = sum(max(0, min(self.contrib[s], cap) - prev) for s in SEATS)
            if amount > 0:
                pots.append({"amount": amount, "eligible": [s for s in live if self.contrib[s] >= cap]})
            prev = cap
        return pots or [{"amount": 0, "eligible": live}]

    def can_edit_stacks(self) -> bool:
        return self.phase in ("waiting", "showdown")

    def snapshot(self) -> dict[str, Any]:
        cfg = self.config
        players = []
        for seat in SEATS:
            name = self.names[seat]
            if name is None:
                status = "empty"
            elif seat in self.folded:
                status = "folded"
            elif seat in self.all_in:
                status = "all_in"
            else:
                status = "active"
            players.append({
                "seat": seat,
                "name": name,
                "stack": self.stack[seat] if name else 0,
                "status": status,
                "bet": self.in_street.get(seat, 0),
                "lastAction": self.last_action.get(seat),
                "cards": len(self.dealt.get(seat, [])) if seat in self.registered else 0,
                "isButton": seat == self.button and name is not None,
                "hands": self.hands[seat] if name else 0,
                "buyIn": self.buy_in[seat] if name else 0,
                "cashedOut": self.cashed_out[seat] if name else 0,
                "net": (self.stack[seat] + self.cashed_out[seat] - self.buy_in[seat]) if name else 0,
            })
        pending = None
        if self.pending:
            pending = {
                "config": self.pending,
                "label": game_label(self.pending),
                "blinds": f"{self.pending['sb']}/{self.pending['bb']}",
            }
        in_hand = self.phase not in ("waiting",)
        return {
            "version": self.version,
            "hand": self.hand,
            "gameLabel": game_label(cfg),
            "config": cfg,
            "blinds": self.blinds,
            "button": self.button,
            "street": self.street,
            "phase": self.phase,
            "toAct": self.to_act,
            "order": self.order,
            "players": players,
            "pots": self.pots_final if self.pots_final is not None else self.pots_now(),
            "boards": [b[: self.revealed] for b in self.boards],
            "holeCards": hole_cards(cfg),
            "pending": pending,
            "options": {"variants": VARIANTS, "blindPresets": BLIND_PRESETS},
            "inactive": [
                {**e, "net": e["stack"] + e["cashedOut"] - e["buyIn"]} for e in self.inactive
            ],
            "canShowdown": self.phase == "showdown_ready",
            "canNextHand": self.phase == "showdown",
            "canEditStacks": self.can_edit_stacks(),
            "uncontested": in_hand and len([s for s in self.dealt if s not in self.folded]) == 1,
            "showdown": self.result,
            "note": self.note,
            "game": {
                "startedAt": self.game_started.isoformat(timespec="seconds"),
                "handsPlayed": self.game_hands,
            },
            "lastSummary": self.last_summary,
        }

    async def publish(self) -> None:
        self.version += 1
        await self.hub.publish(self.snapshot())

    # --------------------------------------------------------------- equity

    def _schedule_equity(self) -> None:
        """Compute equity and outs off the event loop; only the newest request is sent."""
        self._eq_gen += 1
        asyncio.create_task(self._equity(self._eq_gen))

    async def _equity(self, gen: int) -> None:
        live = [s for s in self.order if s not in self.folded and s in self.registered]
        if len(live) < 2:
            return
        game = self.config["variant"]
        holes = {s: self.dealt[s] for s in live}
        boards = [b[: self.revealed] for b in self.boards]
        samples = 500 if game == "nlh" else 250
        hand = self.hand

        def work() -> tuple[dict[int, float], dict[int, list[str]]]:
            per_board = [equity.equities(game, holes, b, samples) for b in boards]
            eq = {s: sum(e[s] for e in per_board) / len(per_board) for s in live}
            hints = equity.outs(game, holes, boards[0]) if len(boards) == 1 else {}
            return eq, hints

        eq, hints = await asyncio.to_thread(work)
        if gen != self._eq_gen or hand != self.hand or self.phase in ("showdown", "waiting"):
            return                                   # something newer has happened
        await self.hub.emit({
            "type": "equity",
            "equities": {str(s): round(v, 1) for s, v in eq.items()},
            "outs": {str(s): cards for s, cards in hints.items()},
        })

    # ------------------------------------------------------------- commands

    def _seat_arg(self, msg: dict, occupied: bool | None = True) -> tuple[int | None, str | None]:
        seat = msg.get("seat")
        if seat not in SEATS:
            return None, "Unknown seat."
        if occupied is True and self.names[seat] is None:
            return None, f"Seat {seat} is empty."
        if occupied is False and self.names[seat] is not None:
            return None, f"Seat {seat} is taken."
        return seat, None

    @staticmethod
    def _amount(value: Any) -> int | None:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return None
        return n

    async def command(self, msg: dict) -> str | None:
        cmd = msg.get("cmd")

        if cmd == "showdown":
            if self.phase != "showdown_ready":
                return "The hand isn't ready for showdown yet."
            self._showdown.set()

        elif cmd == "next_hand":
            if self.phase != "showdown":
                return "Show the result before starting the next hand."
            self._next.set()

        elif cmd == "set_config":
            return await self._set_config(msg.get("config") or {})

        elif cmd == "edit_name":
            seat, err = self._seat_arg(msg)
            if err:
                return err
            name = str(msg.get("name", "")).strip()
            if not 1 <= len(name) <= 16:
                return "A name needs 1 to 16 characters."
            self.names[seat] = name
            await self.publish()

        elif cmd == "adjust_stack":
            if not self.can_edit_stacks():
                return "Stacks can only be changed between hands."
            seat, err = self._seat_arg(msg)
            if err:
                return err
            amount = self._amount(msg.get("amount"))
            if not amount:
                return "Enter an amount."
            if amount > 0:
                self.stack[seat] += amount
                self.buy_in[seat] += amount
            else:
                take = -amount
                if take > self.stack[seat]:
                    return f"{self.names[seat]} only has ${self.stack[seat]}."
                self.stack[seat] -= take
                self.cashed_out[seat] += take
            await self.publish()

        elif cmd == "remove_player":
            if not self.can_edit_stacks():
                return "Players can only be removed between hands."
            seat, err = self._seat_arg(msg)
            if err:
                return err
            self.inactive.append({
                "id": self._next_id,
                "name": self.names[seat],
                "stack": self.stack[seat],          # what they left with
                "buyIn": self.buy_in[seat],
                "cashedOut": self.cashed_out[seat],
                "hands": self.hands[seat],
            })
            self._next_id += 1
            self.names[seat] = None
            self.stack[seat] = 0
            self.buy_in[seat] = 0
            self.cashed_out[seat] = 0
            self.hands[seat] = 0
            await self.publish()

        elif cmd == "seat_returning":
            if not self.can_edit_stacks():
                return "Players can only be seated between hands."
            seat, err = self._seat_arg(msg, occupied=False)
            if err:
                return err
            entry = next((e for e in self.inactive if e["id"] == msg.get("id")), None)
            if entry is None:
                return "That player is not on the inactive list."
            stack = self._amount(msg.get("stack"))
            if not stack or stack <= 0:
                return "Enter a stack to sit down with."
            # coming back with more is an add-on; with less, the difference was taken off
            buy_in, cashed = entry["buyIn"], entry["cashedOut"]
            if stack > entry["stack"]:
                buy_in += stack - entry["stack"]
            else:
                cashed += entry["stack"] - stack
            self.names[seat] = entry["name"]
            self.stack[seat] = stack
            self.buy_in[seat] = buy_in
            self.cashed_out[seat] = cashed
            self.hands[seat] = entry.get("hands", 0)
            self.inactive.remove(entry)
            await self.publish()

        elif cmd == "add_player":
            if not self.can_edit_stacks():
                return "Players can only be added between hands."
            seat, err = self._seat_arg(msg, occupied=False)
            if err:
                return err
            name = str(msg.get("name", "")).strip()
            stack = self._amount(msg.get("stack"))
            if not 1 <= len(name) <= 16:
                return "A name needs 1 to 16 characters."
            if not stack or stack <= 0:
                return "Enter a buy-in amount."
            self.names[seat] = name
            self.stack[seat] = stack
            self.buy_in[seat] = stack
            self.cashed_out[seat] = 0
            self.hands[seat] = 0
            await self.publish()

        elif cmd == "new_game":
            return await self._new_game()

        else:
            return f"Unknown command {cmd!r}."
        return None

    # ------------------------------------------------------------ new game

    def _summary(self, ended: datetime) -> dict[str, Any]:
        rows = []
        for seat in SEATS:
            if self.names[seat] is None:
                continue
            rows.append({
                "name": self.names[seat], "seat": seat, "status": "seated",
                "handsPlayed": self.hands[seat], "buyIn": self.buy_in[seat],
                "cashedOut": self.cashed_out[seat], "endingStack": self.stack[seat],
                "net": self.stack[seat] + self.cashed_out[seat] - self.buy_in[seat],
            })
        for e in self.inactive:
            rows.append({
                "name": e["name"], "seat": None, "status": "left",
                "handsPlayed": e.get("hands", 0), "buyIn": e["buyIn"],
                "cashedOut": e["cashedOut"], "endingStack": e["stack"],
                "net": e["stack"] + e["cashedOut"] - e["buyIn"],
            })
        rows.sort(key=lambda r: r["net"], reverse=True)
        cfg = self.config
        return {
            "startedAt": self.game_started.isoformat(timespec="seconds"),
            "endedAt": ended.isoformat(timespec="seconds"),
            "handsPlayed": self.game_hands,
            "game": {"label": game_label(cfg), "blinds": self.blinds, "bombPot": cfg["bomb"],
                     "ante": cfg["ante"] if cfg["bomb"] else None, "config": cfg},
            "players": rows,
            "totals": {
                "buyIn": sum(r["buyIn"] for r in rows),
                "endingStack": sum(r["endingStack"] for r in rows),
                "cashedOut": sum(r["cashedOut"] for r in rows),
                "net": sum(r["net"] for r in rows),
            },
        }

    def _save_summary(self, summary: dict[str, Any], ended: datetime) -> str:
        GAMES_DIR.mkdir(parents=True, exist_ok=True)
        stem = f"game-{ended.strftime('%Y%m%d-%H%M%S')}"
        (GAMES_DIR / f"{stem}.json").write_text(json.dumps(summary, indent=2) + "\n")
        with (GAMES_DIR / f"{stem}.csv").open("w", newline="") as f:
            out = csv.writer(f)
            out.writerow(["player", "hands_played", "bought_in", "cashed_out", "ending_stack", "net"])
            for r in summary["players"]:
                out.writerow([r["name"], r["handsPlayed"], r["buyIn"], r["cashedOut"],
                              r["endingStack"], r["net"]])
        try:
            return str((GAMES_DIR / f"{stem}.json").relative_to(Path(__file__).resolve().parents[1]))
        except ValueError:
            return str(GAMES_DIR / f"{stem}.json")

    async def _new_game(self) -> str | None:
        """Save a summary of this game, clear the seats, keep the settings."""
        if self.phase not in ("waiting", "showdown"):
            return "Finish the hand before starting a new game."
        ended = datetime.now()
        if self.phase == "showdown":
            self.game_hands += 1                     # the hand on screen is finished
        summary = self._summary(ended)
        if not summary["players"]:
            if self.phase == "showdown":
                self.game_hands -= 1
            return "There is nothing to save yet: no players have sat down."
        saved = self._save_summary(summary, ended)

        # a queued settings change is part of "the settings selected": use it
        if self.pending:
            self.config, self.pending = self.pending, None

        for s in SEATS:
            self.names[s] = None
            self.stack[s] = 0
            self.buy_in[s] = 0
            self.cashed_out[s] = 0
            self.hands[s] = 0
        self.inactive = []
        self.hand = 0
        self.game_hands = 0
        self.game_started = datetime.now()
        self.button = SEATS[-1]
        self.last_summary = {
            "file": saved, "savedAt": ended.isoformat(timespec="seconds"),
            "handsPlayed": summary["handsPlayed"], "players": len(summary["players"]),
        }

        if self.phase == "showdown":
            self._abort_for_new_game = True          # unblock the hand waiting on Next Hand
            self._reset()
            self.phase = "waiting"
            self._next.set()
        else:
            self._reset()
            self.phase = "waiting"
        await self.publish()
        return None

    async def _set_config(self, changes: dict) -> str | None:
        merged = dict(self.pending or self.config)
        merged.update({k: v for k, v in changes.items() if k in DEFAULT_CONFIG})
        if merged["variant"] not in VARIANTS:
            return f"Unknown game {merged['variant']!r}."
        if merged["boards"] not in (1, 2):
            return "Boards must be 1 or 2."
        merged["bomb"] = bool(merged["bomb"])
        for key in ("ante", "sb", "bb"):
            value = self._amount(merged[key])
            if value is None or value < 0:
                return f"{key} must be a whole number."
            merged[key] = value
        if merged["sb"] < 1 or merged["bb"] < merged["sb"]:
            return "Blinds need a small blind of at least 1, and a big blind at least as big."
        self.pending = None if merged == self.config else merged
        await self.publish()
        return None

    # ------------------------------------------------------------ betting

    def _put(self, seat: int, amount: int) -> None:
        self.stack[seat] -= amount
        self.in_street[seat] = self.in_street.get(seat, 0) + amount
        self.contrib[seat] += amount
        if self.stack[seat] == 0 and amount > 0:
            self.all_in.add(seat)

    def _act(self, seat: int, kind: str, to: int | None) -> dict:
        if kind == "call" and to is None:
            to = max([0] + list(self.in_street.values()))
        amount = 0
        if kind == "all_in":
            amount = self.stack[seat]
            to = self.in_street.get(seat, 0) + amount
        elif to is not None:
            amount = min(self.stack[seat], to - self.in_street.get(seat, 0))
            if amount == self.stack[seat] and amount > 0:
                kind = "all_in"
                to = self.in_street.get(seat, 0) + amount
        self._put(seat, amount)
        if kind == "fold":
            self.folded.add(seat)
        words = {"check": "CHECK", "fold": "FOLD", "call": f"CALL ${to}", "bet": f"BET ${to}",
                 "raise": f"RAISE ${to}", "all_in": f"ALL-IN ${to}"}
        self.last_action[seat] = words[kind]
        return {"type": "action", "seat": seat, "action": kind, "amount": to,
                "stack": self.stack[seat], "pots": self.pots_now()}

    async def _step(self, seat: int, kind: str, to: int | None = None, pause: float = 1.3) -> None:
        self.to_act, self.phase = seat, "betting"
        await self.hub.emit({"type": "turn", "seat": seat})
        await self.publish()
        await self.hub.emit(self._act(seat, kind, to))
        await self.publish()
        if kind == "fold":
            self._schedule_equity()
        await sleep(pause)

    async def _post(self, seat: int, kind: str, amount: int) -> None:
        amount = min(amount, self.stack[seat])
        self._put(seat, amount)
        self.last_action[seat] = f"{kind} ${amount}"
        await self.hub.emit({"type": "blind", "seat": seat, "kind": kind, "amount": amount,
                             "stack": self.stack[seat], "pots": self.pots_now()})
        await self.publish()

    async def _street(self, name: str, count: int) -> None:
        self.in_street.clear()
        self.last_action.clear()
        self.street, self.revealed, self.to_act = name, count, None
        boards = [b[:count] for b in self.boards]
        event = {"type": "street", "street": name, "pots": self.pots_now()}
        event.update({"boards": boards} if len(boards) > 1 else {"board": boards[0]})
        await self.hub.emit(event)
        await self.publish()
        self._schedule_equity()
        await sleep(1.6)

    def _live(self) -> list[int]:
        return [s for s in self.order if s not in self.folded]

    # --------------------------------------------------------------- a hand

    async def play_hand(self) -> None:
        while len(self.seated()) < MIN_PLAYERS:
            self._reset()
            self.phase = "waiting"
            self.note = f"Waiting for players ({len(self.seated())} seated, {MIN_PLAYERS} needed)."
            await self.publish()
            await asyncio.sleep(0.5)
        self.note = None

        self.hand += 1
        if self.pending:
            self.config, self.pending = self.pending, None
        self._reset()

        cfg = self.config
        bomb = cfg["bomb"]
        holes = hole_cards(cfg)
        sb_amt, bb_amt = cfg["sb"], cfg["bb"]

        # felted players are topped up automatically
        for seat in self.seated():
            if self.stack[seat] < bb_amt:
                topup = AUTO_REBUY - self.stack[seat]
                self.stack[seat] += topup
                self.buy_in[seat] += topup

        seated = self.seated()
        if self.button not in seated:
            after = [s for s in seated if s > self.button]
            self.button = (after or seated)[0]
        order = [s for s in seated if s > self.button] + [s for s in seated if s <= self.button]
        sb, bb, *rest = order
        self.order = order

        deck = [r + s for r in CARD_ORDER for s in "shdc"]
        random.shuffle(deck)
        for i, seat in enumerate(order):
            self.dealt[seat] = deck[i * holes:(i + 1) * holes]
        extra = deck[len(order) * holes:]
        self.boards = [extra[i * 5:(i + 1) * 5] for i in range(cfg["boards"])]
        self.revealed = 0

        for seat in order:
            self.hands[seat] += 1

        players = [{"seat": s, "name": self.names[s], "stack": self.stack[s]} for s in order]
        await self.hub.emit({"type": "hand_start", "hand": self.hand, "game": game_label(cfg),
                             "hole_cards": holes, "blinds": self.blinds, "button": self.button,
                             "players": players, "order": order, "pots": [0]})
        await self.publish()
        await sleep(1.2)

        reg = list(order)
        random.shuffle(reg)                     # hole cards register in no set order
        for seat in reg:
            self.registered.add(seat)
            await self.hub.emit({"type": "cards", "seat": seat, "cards": self.dealt[seat]})
            await self.publish()
            await sleep(0.45)
        self._schedule_equity()
        await sleep(0.6)

        if bomb:
            await self._bomb_pot(order, sb, bb, bb_amt, cfg["ante"])
        elif self.hand % 4 == 0:
            await self._uncontested(sb, bb, rest, sb_amt, bb_amt)
        else:
            await self._shove_fest(sb, bb, rest, sb_amt, bb_amt)

        # betting is over: wait for the dealer to call showdown
        self.to_act, self.phase = None, "showdown_ready"
        await self.publish()
        await self._showdown.wait()
        self._showdown.clear()

        await self._compute_result()
        self.phase = "showdown"
        await self.publish()
        await self._next.wait()
        self._next.clear()

        if self._abort_for_new_game:
            # the dealer started a new game instead: clear the overlay and stop
            self._abort_for_new_game = False
            await self.hub.emit({"type": "next_hand", "winners": []})
            return
        self.game_hands += 1

        winners = [{"seat": w["seat"], "amount": w["won"], "stack": self.stack[w["seat"]]}
                   for w in self.result["players"] if w["won"] > 0]
        await self.hub.emit({"type": "next_hand", "winners": winners})

        seated = self.seated()
        after = [s for s in seated if s > self.button] or seated
        self.button = after[0] if after else self.button

    async def _run_out(self) -> None:
        if len(self._live()) < 2:
            return
        await sleep(0.8)
        await self._street("flop", 3)
        await self._street("turn", 4)
        await self._street("river", 5)

    async def _shove_fest(self, sb, bb, rest, sb_amt, bb_amt) -> None:
        """Short stacks shove one after another: a main pot and side pots."""
        await self._post(sb, "SB", sb_amt)
        await self._post(bb, "BB", bb_amt)
        await self.hub.emit({"type": "turn", "seat": rest[0]})
        self.to_act, self.phase = rest[0], "betting"
        await self.publish()
        await sleep(2.2)

        actors = rest + [sb, bb]
        shovers = set(random.sample(actors, min(3, len(actors))))
        for seat in actors:
            if seat in self.all_in:
                continue
            await self._step(seat, "all_in" if seat in shovers else "fold")
        await self._run_out()

    async def _uncontested(self, sb, bb, rest, sb_amt, bb_amt) -> None:
        await self._post(sb, "SB", sb_amt)
        await self._post(bb, "BB", bb_amt)
        await sleep(1.0)
        await self._step(rest[0], "raise", 3 * bb_amt)
        for seat in (*rest[1:], sb, bb):
            if seat not in self.all_in:
                await self._step(seat, "fold", pause=0.9)
        self.to_act = None

    async def _bomb_pot(self, order, sb, bb, bb_amt, ante) -> None:
        """Everyone antes; no preflop betting; straight to the flop."""
        for seat in order:
            await self._post(seat, "ANTE", ante)
        await sleep(0.4)
        await self._street("flop", 3)

        acting = [s for s in order if s not in self.all_in]
        if len(acting) >= 2:
            keep = set(random.sample(acting, min(3, len(acting))))
            first = next(s for s in acting if s in keep)
            await self._step(first, "bet", 4 * bb_amt)
            for seat in acting:
                if seat == first:
                    continue
                await self._step(seat, "call" if seat in keep else "fold", pause=0.9)
            contenders = [s for s in acting if s in keep and s not in self.all_in]

            await self._street("turn", 4)
            if len(contenders) >= 2:
                await self._step(contenders[0], "check")
                await self._step(contenders[1], "bet", 8 * bb_amt)
                for seat in contenders[2:] + contenders[:1]:
                    await self._step(seat, "call", 8 * bb_amt)
            await self._street("river", 5)
        else:
            await self._run_out()

    # ------------------------------------------------------------- showdown

    async def _compute_result(self) -> None:
        pots = self.pots_now()
        self.pots_final = pots
        order = self.order
        live = [s for s in order if s not in self.folded]
        before = {s: self.stack[s] for s in order}
        won = {s: 0 for s in order}
        shared: set[int] = set()
        variant = self.config["variant"]

        def evaluate(seat: int, board: list[str]):
            hole = list(Card.parse("".join(self.dealt[seat])))
            cards = list(Card.parse("".join(board)))
            cls = StandardHighHand if variant == "nlh" else OmahaHoldemHand
            return cls.from_game(hole, cards)

        if len(live) == 1:
            winner = live[0]
            total = sum(p["amount"] for p in pots)
            self.stack[winner] += total
            self.result = {
                "contested": False,
                "boards": [],
                "players": [{
                    "seat": winner, "name": self.names[winner], "cards": [], "hands": [],
                    "won": total, "stackBefore": before[winner],
                    "stackAfter": self.stack[winner], "result": "win",
                }],
                "pots": [{"label": "Pot", "amount": total, "eligible": [winner],
                          "winners": [{"seat": winner, "amount": total}], "boards": []}],
            }
            return

        boards = [b[:5] for b in self.boards]
        hands = {s: [evaluate(s, b) for b in boards] for s in live}
        pot_rows = []
        for i, pot in enumerate(pots):
            n_boards = len(boards)
            each_board = pot["amount"] // n_boards
            shares = [pot["amount"] - (n_boards - 1) * each_board] + [each_board] * (n_boards - 1)
            payouts: dict[int, int] = {}
            board_rows = []
            for b, share in enumerate(shares):
                contenders = [s for s in order if s in pot["eligible"] and s in hands]
                best = max(hands[s][b] for s in contenders)
                winners = [s for s in contenders if hands[s][b] == best]
                each, extra = divmod(share, len(winners))
                for k, s in enumerate(winners):
                    payouts[s] = payouts.get(s, 0) + each + (extra if k == 0 else 0)
                if len(winners) > 1:
                    shared.update(winners)
                board_rows.append({"board": b, "winners": winners, "hand": str(best.entry.label)})
            for s, amount in payouts.items():
                won[s] += amount
            label = "Pot" if len(pots) == 1 else "Main Pot" if i == 0 else f"Side Pot {i}"
            pot_rows.append({
                "label": label, "amount": pot["amount"], "eligible": pot["eligible"],
                "winners": [{"seat": s, "amount": a} for s, a in payouts.items()],
                "boards": board_rows,
            })

        for s in order:
            self.stack[s] += won[s]
        self.result = {
            "contested": True,
            "boards": boards,
            "players": [{
                "seat": s, "name": self.names[s], "cards": self.dealt[s],
                "hands": [{"label": str(h.entry.label), "cards": [repr(c) for c in h.cards]}
                          for h in hands[s]],
                "won": won[s], "stackBefore": before[s], "stackAfter": self.stack[s],
                "result": ("split" if s in shared and won[s] > 0 else "win" if won[s] > 0 else "lose"),
            } for s in live],
            "pots": pot_rows,
        }

    # ------------------------------------------------------------------ run

    async def run(self) -> None:
        while True:
            try:
                await self.play_hand()
            except asyncio.CancelledError:
                raise
            except Exception:                       # keep the table alive
                import traceback
                traceback.print_exc()
                await asyncio.sleep(2)
