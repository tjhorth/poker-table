"""Win equity and "outs" for the hands still in a pot.

Both are computed from the live players' hole cards and the board only. Cards
held by players who folded are treated as unseen, which matches what a viewer
could know.
"""

from __future__ import annotations

import itertools
import math
import random

from pokerkit import Card, OmahaHoldemHand, StandardHighHand

RANKS = "AKQJT98765432"
DECK = [r + s for r in RANKS for s in "shdc"]
_CARD = {c: next(iter(Card.parse(c))) for c in DECK}


def _evaluate(game: str, hole: list[str], board: list[str]):
    cls = StandardHighHand if game == "nlh" else OmahaHoldemHand
    return cls.from_game([_CARD[c] for c in hole], [_CARD[c] for c in board])


def _unseen(holes: dict[int, list[str]], board: list[str]) -> list[str]:
    known = set(board).union(*holes.values()) if holes else set(board)
    return [c for c in DECK if c not in known]


def equities(game: str, holes: dict[int, list[str]], board: list[str],
             samples: int = 500, rng: random.Random | None = None) -> dict[int, float]:
    """Each player's chance of winning the pot, with ties split, in percent."""
    seats = list(holes)
    if len(seats) < 2:
        return {s: 100.0 for s in seats}
    rng = rng or random.Random()
    unseen = _unseen(holes, board)
    need = 5 - len(board)

    if need <= 0:
        combos: list[tuple[str, ...]] = [()]
    elif math.comb(len(unseen), need) <= samples * 2:
        combos = list(itertools.combinations(unseen, need))
    else:
        combos = [tuple(rng.sample(unseen, need)) for _ in range(samples)]

    score = {s: 0.0 for s in seats}
    for extra in combos:
        full = board + list(extra)
        hands = {s: _evaluate(game, holes[s], full) for s in seats}
        best = max(hands.values())
        winners = [s for s in seats if hands[s] == best]
        for s in winners:
            score[s] += 1 / len(winners)
    return {s: 100 * score[s] / len(combos) for s in seats}


def outs(game: str, holes: dict[int, list[str]], board: list[str]) -> dict[int, list[str]]:
    """For each player who is currently behind: the next cards that would put
    them strictly in the lead. Only defined on the flop and the turn."""
    seats = list(holes)
    if len(seats) < 2 or len(board) not in (3, 4):
        return {}
    now = {s: _evaluate(game, holes[s], board) for s in seats}
    best = max(now.values())
    behind = [s for s in seats if now[s] != best]
    if not behind:
        return {}

    found: dict[int, list[str]] = {s: [] for s in behind}
    for card in _unseen(holes, board):
        hands = {s: _evaluate(game, holes[s], board + [card]) for s in seats}
        top = max(hands.values())
        leaders = [s for s in seats if hands[s] == top]
        if len(leaders) == 1 and leaders[0] in found:
            found[leaders[0]].append(card)
    return {s: cards for s, cards in found.items() if cards}
