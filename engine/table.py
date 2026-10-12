"""The game engine: the rules of the table.

Nothing in here touches the network, the clock, or a database. Everything the
engine knows arrives as an *observed event* (cards registered, a blind or a
bet seen in a bet zone, a board registered) or a *dealer command* (showdown,
next hand, seat changes). The engine checks each one against the rules, updates
its state, and reports what changed through three subscriber lists:

    on_state(snapshot)    full snapshot for the dealer UI after every change
    on_overlay(event)     ordered event stream for the stream overlay
    on_equity(request)    "recompute equity for these hands" (heavy work is
                          left to the caller, so the engine stays fast)

Every public input method returns None on success, or a short message
explaining why the input was refused (state is left unchanged).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Callable

from pokerkit import Card, OmahaHoldemHand, StandardHighHand

SEATS = list(range(1, 9))
MIN_PLAYERS = 2
AUTO_REBUY = 200            # a player who cannot post a blind is topped up to this
VARIANTS = {"nlh": "NLH", "plo4": "PLO 4-card"}
BLIND_PRESETS = ["1/2", "2/5", "5/10", "10/20", "25/50"]
DEFAULT_CONFIG: dict[str, Any] = {
    "variant": "nlh", "boards": 1, "bomb": False, "ante": 5, "sb": 1, "bb": 2,
}
RANKS = "AKQJT98765432"
DECK = [r + s for r in RANKS for s in "shdc"]
BOARD_SIZE = {"flop": 3, "turn": 4, "river": 5}
NEXT_STREET = {"preflop": "flop", "flop": "turn", "turn": "river"}

PHASES = ("waiting", "dealing", "blinds", "betting", "awaiting_board", "showdown_ready", "showdown")


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


class Table:
    def __init__(self, summary_sink: Callable[[dict], str] | None = None) -> None:
        self.summary_sink = summary_sink
        self.on_state: list[Callable[[dict], None]] = []
        self.on_overlay: list[Callable[[dict], None]] = []
        self.on_equity: list[Callable[[dict], None]] = []

        self.config: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.pending: dict[str, Any] | None = None
        self.version = 0
        self.note: str | None = None

        # who is at the table; kept from hand to hand
        self.names: dict[int, str | None] = {s: None for s in SEATS}
        self.stack = {s: 0 for s in SEATS}
        self.buy_in = {s: 0 for s in SEATS}
        self.cashed_out = {s: 0 for s in SEATS}
        self.hands = {s: 0 for s in SEATS}
        self.inactive: list[dict[str, Any]] = []
        self._next_id = 1

        # the game as a whole
        self.hand = 0
        self.button = SEATS[-1]
        self.game_hands = 0
        self.game_started = datetime.now()
        self.last_summary: dict[str, Any] | None = None

        self._reset_hand()
        self.phase = "waiting"

    # ====================================================== subscriptions

    def _emit(self, event: dict) -> None:
        for cb in self.on_overlay:
            cb(event)

    def _changed(self) -> None:
        self.version += 1
        snap = self.snapshot()
        for cb in self.on_state:
            cb(snap)

    def _request_equity(self) -> None:
        live = [s for s in self.order if s not in self.folded and s in self.dealt]
        if len(live) < 2 or not self.dealt:
            return
        request = {
            "hand": self.hand,
            "variant": self.config["variant"],
            "holes": {s: list(self.dealt[s]) for s in live},
            "boards": [list(b) for b in self.boards],
        }
        for cb in self.on_equity:
            cb(request)

    # ============================================================ state

    def _reset_hand(self) -> None:
        self.phase = "waiting"
        self.street = "preflop"
        self.to_act: int | None = None
        self.order: list[int] = []         # small blind first
        self.pre_order: list[int] = []
        self.post_order: list[int] = []
        self.contrib = {s: 0 for s in SEATS}
        self.in_street: dict[int, int] = {}
        self.folded: set[int] = set()
        self.all_in: set[int] = set()
        self.last_action: dict[int, str] = {}
        self.dealt: dict[int, list[str]] = {}
        self.boards: list[list[str]] = []
        self.expect_street: str | None = None
        self.blind_plan: list[tuple[int, str, int]] = []
        self.ante_due: set[int] = set()
        self.current_bet = 0
        self.last_raise = 0
        self.acted: set[int] = set()
        self.last_actor: int | None = None
        self._seq: list[int] = []
        self.result: dict | None = None
        self.pots_final: list[dict] | None = None

    def seated(self) -> list[int]:
        return [s for s in SEATS if self.names[s] is not None]

    @property
    def blinds(self) -> str:
        return f"{self.config['sb']}/{self.config['bb']}"

    @property
    def bomb(self) -> bool:
        return bool(self.config["bomb"])

    def _live(self) -> list[int]:
        return [s for s in self.order if s not in self.folded]

    def _can_act(self, seat: int) -> bool:
        return seat not in self.folded and seat not in self.all_in and self.stack[seat] > 0

    def can_edit_stacks(self) -> bool:
        return self.phase in ("waiting", "showdown")

    # ---------------------------------------------------------------- pots

    def pots(self) -> list[dict]:
        """Main pot plus side pots; a new pot starts above each all-in level."""
        live = self._live()
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

    # --------------------------------------------------------- what's next

    def legal(self) -> dict[str, Any] | None:
        """What the player on action may do, for the dealer UI and for sensors."""
        seat = self.to_act
        if seat is None or self.phase != "betting":
            return None
        mine = self.in_street.get(seat, 0)
        to_call = max(0, self.current_bet - mine)
        reach = mine + self.stack[seat]                       # all-in "to" amount
        top = reach
        if self.config["variant"] != "nlh":                   # pot limit
            pot = sum(self.contrib.values())
            top = min(reach, self.current_bet + pot + to_call)
        floor = self.current_bet + self.last_raise if self.current_bet > 0 else self.config["bb"]
        return {
            "seat": seat,
            "currentBet": self.current_bet,
            "toCall": min(to_call, self.stack[seat]),
            "canCheck": to_call == 0,
            "minRaiseTo": min(floor, top),
            "maxRaiseTo": top,
            "allInTo": reach,
            "potLimit": self.config["variant"] != "nlh",
        }

    def awaiting(self) -> dict[str, Any]:
        """The next input the engine needs. Sensors and drivers read this."""
        if self.phase == "dealing" or self.phase == "blinds":
            missing = [s for s in self.order if s not in self.dealt]
            out: dict[str, Any] = {"kind": "cards", "seats": missing, "count": hole_cards(self.config)}
            if not missing:
                out = {"kind": "blinds"}
            if self.bomb and self.ante_due:
                out["antes"] = sorted(self.ante_due)
            elif self.blind_plan:
                s, kind, amount = self.blind_plan[0]
                out["blind"] = {"seat": s, "kind": kind, "amount": min(amount, self.stack[s])}
            return out
        if self.phase == "betting":
            return {"kind": "action", "seat": self.to_act, "legal": self.legal()}
        if self.phase == "awaiting_board":
            return {"kind": "board", "street": self.expect_street,
                    "cards": BOARD_SIZE[self.expect_street or "flop"], "boards": self.config["boards"]}
        if self.phase == "showdown_ready":
            return {"kind": "showdown"}
        if self.phase == "showdown":
            return {"kind": "next_hand"}
        return {"kind": "players", "needed": MIN_PLAYERS}

    # ---------------------------------------------------------- snapshot

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
                "cards": len(self.dealt.get(seat, [])),
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
        live_count = len(self._live())
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
            "legal": self.legal(),
            "awaiting": self.awaiting(),
            "order": self.order,
            "players": players,
            "pots": self.pots_final if self.pots_final is not None else self.pots(),
            "boards": [list(b) for b in self.boards],
            "holeCards": hole_cards(cfg),
            "pending": pending,
            "options": {"variants": VARIANTS, "blindPresets": BLIND_PRESETS},
            "inactive": [
                {**e, "net": e["stack"] + e["cashedOut"] - e["buyIn"]} for e in self.inactive
            ],
            "canDeal": self.phase == "waiting" and len(self.seated()) >= MIN_PLAYERS,
            "canShowdown": self.phase == "showdown_ready",
            "canNextHand": self.phase == "showdown",
            "canEditStacks": self.can_edit_stacks(),
            "uncontested": bool(self.order) and live_count == 1 and self.phase != "waiting",
            "showdown": self.result,
            "note": self.note,
            "game": {
                "startedAt": self.game_started.isoformat(timespec="seconds"),
                "handsPlayed": self.game_hands,
            },
            "lastSummary": self.last_summary,
        }

    # ========================================================= hand flow

    def _start_hand_or_wait(self) -> None:
        seated = self.seated()
        if len(seated) < MIN_PLAYERS:
            self._reset_hand()
            self.phase = "waiting"
            self.note = f"Waiting for players ({len(seated)} seated, {MIN_PLAYERS} needed)."
            return
        self.note = None
        self._start_hand()

    def _start_hand(self) -> None:
        self.hand += 1
        if self.pending:
            self.config, self.pending = self.pending, None
        self._reset_hand()
        cfg = self.config
        sb_amt, bb_amt = cfg["sb"], cfg["bb"]

        # a player who cannot cover the big blind is topped up automatically
        for seat in self.seated():
            if self.stack[seat] < bb_amt:
                topup = AUTO_REBUY - self.stack[seat]
                self.stack[seat] += topup
                self.buy_in[seat] += topup

        seated = self.seated()
        if self.button not in seated:
            # the button seat is empty (first hand, or its player left): put it on the
            # nearest seated player counter-clockwise, so the small blind is the next seat
            before = [s for s in seated if s < self.button]
            self.button = (before or seated)[-1]
        # order[0] is the small blind. Heads-up, the button is the small blind.
        after_button = [s for s in seated if s > self.button] + [s for s in seated if s <= self.button]
        self.order = [after_button[-1]] + after_button[:-1] if len(seated) == 2 else after_button
        n = len(self.order)
        self.pre_order = self.order[2:] + self.order[:2]
        self.post_order = self.order[1:] + self.order[:1] if n == 2 else list(self.order)

        for seat in self.order:
            self.hands[seat] += 1
        sb, bb = self.order[0], self.order[1]
        if self.bomb:
            self.ante_due = set(self.order)
        else:
            self.blind_plan = [(sb, "SB", sb_amt), (bb, "BB", bb_amt)]

        self.phase = "dealing"
        self._emit({
            "type": "hand_start", "hand": self.hand, "game": game_label(cfg),
            "hole_cards": hole_cards(cfg), "blinds": self.blinds, "button": self.button,
            "players": [{"seat": s, "name": self.names[s], "stack": self.stack[s]} for s in self.order],
            "order": self.order, "pots": [0],
        })

    # ------------------------------------------------------- observed input

    def register_cards(self, seat: int, cards: list[str]) -> str | None:
        """A seat's hole cards were read."""
        if self.phase not in ("dealing", "blinds"):
            return "Hole cards are only registered while dealing."
        if seat not in self.order:
            return f"Seat {seat} is not in this hand."
        need = hole_cards(self.config)
        if len(cards) != need:
            return f"This game deals {need} hole cards, but {len(cards)} were read."
        if any(c not in DECK for c in cards) or len(set(cards)) != len(cards):
            return f"Those are not {need} different cards: {cards}."
        taken = {c for s, cs in self.dealt.items() if s != seat for c in cs}
        if taken & set(cards):
            return f"A card in {cards} was already registered at another seat."
        self.dealt[seat] = list(cards)
        self._emit({"type": "cards", "seat": seat, "cards": list(cards)})
        if len(self.dealt) == len(self.order):
            self._request_equity()
        self._check_ready()
        self._changed()
        return None

    def post_blind(self, seat: int, amount: int) -> str | None:
        """A blind (or, in a bomb pot, an ante) was seen in a bet zone."""
        if self.phase not in ("dealing", "blinds"):
            return "Blinds are only posted at the start of a hand."
        if self.bomb:
            if seat not in self.ante_due:
                return f"Seat {seat} has no ante to post."
            expected = min(self.config["ante"], self.stack[seat])
            kind = "ANTE"
        else:
            if not self.blind_plan:
                return "The blinds are already posted."
            due_seat, kind, due = self.blind_plan[0]
            if seat != due_seat:
                return f"The {kind} comes from seat {due_seat}, not seat {seat}."
            expected = min(due, self.stack[seat])
        if amount != expected:
            return f"The {kind} is ${expected}, but ${amount} was seen."
        if self.bomb:
            self.ante_due.discard(seat)
        else:
            self.blind_plan.pop(0)
        self._put(seat, amount)
        self.last_action[seat] = f"{kind} ${amount}"
        self._emit({"type": "blind", "seat": seat, "kind": kind, "amount": amount,
                    "stack": self.stack[seat], "pots": self.pots()})
        self._check_ready()
        self._changed()
        return None

    def _check_ready(self) -> None:
        cards_done = bool(self.order) and len(self.dealt) == len(self.order)
        blinds_done = (not self.ante_due) if self.bomb else (not self.blind_plan)
        if self.phase == "dealing" and cards_done:
            self.phase = "blinds"
        if cards_done and blinds_done and self.phase in ("dealing", "blinds"):
            if self.bomb:
                self._await_board("flop")          # a bomb pot skips preflop betting
            else:
                self._begin_round("preflop")

    def act(self, seat: int, action: str, to: int | None = None) -> str | None:
        """A betting action was observed. `to` is the player's total in front
        this street (what the bet zone shows), for bet / raise."""
        if self.phase != "betting":
            return "There is no betting in progress."
        if seat != self.to_act:
            who = self.names.get(self.to_act) if self.to_act else None
            return f"It is {who or 'someone else'}'s turn (seat {self.to_act}), not seat {seat}."
        legal = self.legal()
        assert legal is not None
        mine = self.in_street.get(seat, 0)
        stack = self.stack[seat]
        to_call = self.current_bet - mine
        kind = action

        if action == "fold":
            put = 0
        elif action == "check":
            if to_call > 0:
                return f"{self.names[seat]} faces ${to_call} and cannot check."
            put = 0
        elif action == "call":
            if to_call <= 0:
                return f"There is nothing to call."
            put = min(stack, to_call)
            kind = "all_in" if put == stack else "call"
        elif action in ("bet", "raise", "all_in"):
            if action == "all_in":
                to = legal["allInTo"]
            if to is None:
                return "A bet or raise needs an amount."
            if action == "bet" and self.current_bet > 0:
                return f"There is already a bet of ${self.current_bet}: that is a raise."
            if action == "raise" and self.current_bet == 0:
                return "There is no bet to raise: that is a bet."
            if to > legal["allInTo"]:
                return f"{self.names[seat]} only has ${stack} behind (${legal['allInTo']} total)."
            if to > legal["maxRaiseTo"]:
                return f"Over the pot limit: the most is ${legal['maxRaiseTo']}."
            is_all_in = to == legal["allInTo"]
            if to <= self.current_bet:
                if not is_all_in:
                    return f"A raise has to be more than ${self.current_bet}."
                put, kind = stack, "all_in"                    # short all-in: a call
            else:
                if to < legal["minRaiseTo"] and not is_all_in:
                    return f"The minimum raise is to ${legal['minRaiseTo']}."
                put = to - mine
                kind = "all_in" if is_all_in else action
        else:
            return f"Unknown action {action!r}."

        # ------- apply
        before = self.current_bet
        if put:
            self._put(seat, put)
        reached = self.in_street.get(seat, 0)
        if action == "fold":
            self.folded.add(seat)
        if reached > before:                                   # a bet or a raise
            size = reached - before
            if size >= self.last_raise or before == 0:         # a full raise reopens the action
                self.acted = set()
                self.last_raise = max(size, self.config["bb"])
            self.current_bet = reached
        self.acted.add(seat)
        self.last_actor = seat

        label = {"check": "CHECK", "fold": "FOLD", "call": f"CALL ${reached}", "bet": f"BET ${reached}",
                 "raise": f"RAISE ${reached}", "all_in": f"ALL-IN ${reached}"}[kind]
        self.last_action[seat] = label
        self._emit({"type": "action", "seat": seat, "action": kind, "amount": reached or None,
                    "stack": self.stack[seat], "pots": self.pots()})
        if action == "fold":
            self._request_equity()

        self._after_action()
        self._changed()
        return None

    def _put(self, seat: int, amount: int) -> None:
        amount = min(amount, self.stack[seat])
        self.stack[seat] -= amount
        self.in_street[seat] = self.in_street.get(seat, 0) + amount
        self.contrib[seat] += amount
        if self.stack[seat] == 0 and amount > 0:
            self.all_in.add(seat)

    def _begin_round(self, street: str) -> None:
        self.street = street
        self.current_bet = max([0] + list(self.in_street.values()))
        self.last_raise = self.config["bb"]
        self.acted = set()
        self.last_actor = None
        self.expect_street = None
        self._seq = self.pre_order if street == "preflop" else self.post_order
        self._after_action()

    def _next_actor(self) -> int | None:
        seq = self._seq
        able = [s for s in seq if s not in self.folded and self._can_act(s)]
        if len(able) <= 1 and all(self.in_street.get(s, 0) >= self.current_bet for s in able):
            return None                                        # nobody left to bet against
        start = 0 if self.last_actor is None else seq.index(self.last_actor) + 1
        for k in range(len(seq)):
            s = seq[(start + k) % len(seq)]
            if s in self.folded or not self._can_act(s):
                continue
            if s not in self.acted or self.in_street.get(s, 0) < self.current_bet:
                return s
        return None

    def _after_action(self) -> None:
        if len(self._live()) == 1:
            self._finish_betting()
            return
        nxt = self._next_actor()
        if nxt is None:
            self._finish_betting()
            return
        self.phase = "betting"
        self.to_act = nxt
        self._emit({"type": "turn", "seat": nxt})

    def _finish_betting(self) -> None:
        self.to_act = None
        if len(self._live()) == 1 or self.street == "river":
            self.phase = "showdown_ready"
        else:
            self._await_board(NEXT_STREET[self.street])

    def _await_board(self, street: str) -> None:
        self.to_act = None
        self.phase = "awaiting_board"
        self.expect_street = street

    def register_board(self, boards: list[list[str]]) -> str | None:
        """Every community card of the next street was read. Send each board's
        full list so far, e.g. [["As","Kd","7c"]] or two lists for double board."""
        if self.phase != "awaiting_board" or self.expect_street is None:
            return "No board cards are expected right now."
        street = self.expect_street
        want = self.config["boards"]
        size = BOARD_SIZE[street]
        if len(boards) != want:
            return f"This game has {want} board(s); {len(boards)} were sent."
        known = {c for cs in self.dealt.values() for c in cs}
        seen: set[str] = set()
        for b, cards in enumerate(boards):
            if len(cards) != size:
                return f"The {street} needs {size} cards on each board, not {len(cards)}."
            if any(c not in DECK for c in cards):
                return f"Not valid cards: {cards}."
            if self.boards and cards[: len(self.boards[b])] != self.boards[b]:
                return "Earlier board cards changed."
            if seen & set(cards) or known & set(cards):
                return f"A card in {cards} is already in play."
            seen |= set(cards)
        self.boards = [list(b) for b in boards]
        self.in_street = {}
        self.last_action = {}
        event: dict[str, Any] = {"type": "street", "street": street, "pots": self.pots()}
        event.update({"boards": self.boards} if want > 1 else {"board": self.boards[0]})
        self._emit(event)
        self._request_equity()
        self._begin_round(street)
        self._changed()
        return None

    # --------------------------------------------------- dealer commands

    def showdown(self) -> str | None:
        if self.phase != "showdown_ready":
            return "The hand isn't ready for showdown yet."
        self._compute_result()
        self.phase = "showdown"
        self._changed()
        return None

    def next_hand(self) -> str | None:
        if self.phase != "showdown":
            return "Show the result before starting the next hand."
        assert self.result is not None
        winners = [{"seat": w["seat"], "amount": w["won"], "stack": self.stack[w["seat"]]}
                   for w in self.result["players"] if w["won"] > 0]
        self._emit({"type": "next_hand", "winners": winners})
        self.game_hands += 1
        seated = self.seated()
        after = [s for s in seated if s > self.button] or seated
        self.button = after[0] if after else self.button
        self._start_hand_or_wait()
        self._changed()
        return None

    # ---------------------------------------------------------- showdown

    def _compute_result(self) -> None:
        pots = self.pots()
        self.pots_final = pots
        order = self.order
        live = self._live()
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
        rows = []
        for i, pot in enumerate(pots):
            label = "Pot" if len(pots) == 1 else "Main Pot" if i == 0 else f"Side Pot {i}"
            if len(pot["eligible"]) == 1 and i > 0:
                # nobody could match this: it is a bet that was never called
                only = pot["eligible"][0]
                won[only] += pot["amount"]
                rows.append({"label": "Uncalled bet returned", "amount": pot["amount"],
                             "eligible": pot["eligible"],
                             "winners": [{"seat": only, "amount": pot["amount"]}], "boards": []})
                continue
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
            rows.append({
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
            "pots": rows,
        }

    # ================================================== seats and ledger

    def _seat_ok(self, seat: Any, occupied: bool | None = True) -> str | None:
        if seat not in SEATS:
            return "Unknown seat."
        if occupied is True and self.names[seat] is None:
            return f"Seat {seat} is empty."
        if occupied is False and self.names[seat] is not None:
            return f"Seat {seat} is taken."
        return None

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _seated_changed(self) -> None:
        """Seats changed. While waiting, just refresh the "need more players" note."""
        if self.phase == "waiting":
            seated = len(self.seated())
            self.note = (
                None if seated >= MIN_PLAYERS
                else f"Waiting for players ({seated} seated, {MIN_PLAYERS} needed)."
            )
        self._changed()

    def deal_hand(self) -> str | None:
        """The dealer starts play from the waiting state."""
        if self.phase != "waiting":
            return "A hand is already in progress."
        if len(self.seated()) < MIN_PLAYERS:
            return f"At least {MIN_PLAYERS} players need to be seated."
        self._start_hand_or_wait()
        self._changed()
        return None

    def edit_name(self, seat: int, name: str) -> str | None:
        if err := self._seat_ok(seat):
            return err
        name = str(name).strip()
        if not 1 <= len(name) <= 16:
            return "A name needs 1 to 16 characters."
        self.names[seat] = name
        self._changed()
        return None

    def adjust_stack(self, seat: int, amount: Any) -> str | None:
        if not self.can_edit_stacks():
            return "Stacks can only be changed between hands."
        if err := self._seat_ok(seat):
            return err
        n = self._int(amount)
        if not n:
            return "Enter an amount."
        if n > 0:
            self.stack[seat] += n
            self.buy_in[seat] += n
        else:
            if -n > self.stack[seat]:
                return f"{self.names[seat]} only has ${self.stack[seat]}."
            self.stack[seat] += n
            self.cashed_out[seat] += -n
        self._changed()
        return None

    def remove_player(self, seat: int) -> str | None:
        if not self.can_edit_stacks():
            return "Players can only be removed between hands."
        if err := self._seat_ok(seat):
            return err
        self.inactive.append({
            "id": self._next_id, "name": self.names[seat], "stack": self.stack[seat],
            "buyIn": self.buy_in[seat], "cashedOut": self.cashed_out[seat], "hands": self.hands[seat],
        })
        self._next_id += 1
        self.names[seat] = None
        for d in (self.stack, self.buy_in, self.cashed_out, self.hands):
            d[seat] = 0
        self._changed()
        return None

    def add_player(self, seat: int, name: str, stack: Any) -> str | None:
        if not self.can_edit_stacks():
            return "Players can only be added between hands."
        if err := self._seat_ok(seat, occupied=False):
            return err
        name = str(name).strip()
        n = self._int(stack)
        if not 1 <= len(name) <= 16:
            return "A name needs 1 to 16 characters."
        if not n or n <= 0:
            return "Enter a buy-in amount."
        self.names[seat], self.stack[seat], self.buy_in[seat] = name, n, n
        self.cashed_out[seat] = self.hands[seat] = 0
        self._seated_changed()
        return None

    def seat_returning(self, seat: int, player_id: Any, stack: Any) -> str | None:
        if not self.can_edit_stacks():
            return "Players can only be seated between hands."
        if err := self._seat_ok(seat, occupied=False):
            return err
        entry = next((e for e in self.inactive if e["id"] == player_id), None)
        if entry is None:
            return "That player is not on the inactive list."
        n = self._int(stack)
        if not n or n <= 0:
            return "Enter a stack to sit down with."
        buy_in, cashed = entry["buyIn"], entry["cashedOut"]
        if n > entry["stack"]:
            buy_in += n - entry["stack"]            # coming back with more: an add-on
        else:
            cashed += entry["stack"] - n            # with less: the difference was taken off
        self.names[seat], self.stack[seat] = entry["name"], n
        self.buy_in[seat], self.cashed_out[seat] = buy_in, cashed
        self.hands[seat] = entry.get("hands", 0)
        self.inactive.remove(entry)
        self._seated_changed()
        return None

    def set_config(self, changes: dict) -> str | None:
        merged = dict(self.pending or self.config)
        merged.update({k: v for k, v in changes.items() if k in DEFAULT_CONFIG})
        if merged["variant"] not in VARIANTS:
            return f"Unknown game {merged['variant']!r}."
        if merged["boards"] not in (1, 2):
            return "Boards must be 1 or 2."
        merged["bomb"] = bool(merged["bomb"])
        for key in ("ante", "sb", "bb"):
            value = self._int(merged[key])
            if value is None or value < 0:
                return f"{key} must be a whole number."
            merged[key] = value
        if merged["sb"] < 1 or merged["bb"] < merged["sb"]:
            return "Blinds need a small blind of at least 1, and a big blind at least as big."
        self.pending = None if merged == self.config else merged
        self._changed()
        return None

    # ---------------------------------------------------------- new game

    def build_summary(self, ended: datetime) -> dict[str, Any]:
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

    def new_game(self) -> str | None:
        """Save a summary of this game, clear the seats, keep the settings."""
        if self.phase not in ("waiting", "showdown"):
            return "Finish the hand before starting a new game."
        ended = datetime.now()
        finished_hand = 1 if self.phase == "showdown" else 0
        self.game_hands += finished_hand
        summary = self.build_summary(ended)
        if not summary["players"]:
            self.game_hands -= finished_hand
            return "There is nothing to save yet: no players have sat down."
        saved = self.summary_sink(summary) if self.summary_sink else None

        if self.pending:                             # a queued change is "the settings selected"
            self.config, self.pending = self.pending, None
        for s in SEATS:
            self.names[s] = None
            self.stack[s] = self.buy_in[s] = self.cashed_out[s] = self.hands[s] = 0
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
            self._emit({"type": "next_hand", "winners": []})    # clears the overlay
        self._reset_hand()
        self.phase = "waiting"
        self.note = f"Waiting for players (0 seated, {MIN_PLAYERS} needed)."
        self._changed()
        return None
