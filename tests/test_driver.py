"""Plays many hands through the real engine with the sensor driver and checks
the invariants that must always hold: no refused inputs, chips conserved."""

import asyncio

from api.driver import LocalPort, SensorDriver
from api.runtime import Runtime


class _Runtime(Runtime):
    """The runtime without its network workers: engine + command mapping only."""


def _chips(t) -> int:
    in_play = sum(t.contrib.values()) if t.phase not in ("showdown",) else 0
    return sum(t.stack[s] for s in t.seated()) + in_play + sum(e["stack"] for e in t.inactive)


async def _play(hands: int, config: dict) -> tuple[SensorDriver, list[int]]:
    rt = _Runtime()
    rt.table.on_equity.clear()              # equity is exercised elsewhere; skip the heavy work
    driver = SensorDriver(LocalPort(rt), speed=0, seed_players=True)
    if config:
        rt.table.set_config(config)
    totals: list[int] = []
    played = 0
    last_hand = 0
    for _ in range(200_000):
        await driver.step()
        t = rt.table
        if t.phase == "showdown_ready":
            assert t.showdown() is None
        elif t.phase == "showdown":
            totals.append(sum(t.stack[s] for s in t.seated()) + sum(e["stack"] for e in t.inactive)
                          - (sum(t.buy_in.values()) - sum(t.cashed_out.values())))
            played += 1
            if played >= hands:
                break
            assert t.next_hand() is None
        last_hand = t.hand
    assert played >= hands, f"only finished {played} hands (stuck at hand {last_hand}, phase {rt.table.phase})"
    return driver, totals


def _run(hands, **config):
    driver, totals = asyncio.run(_play(hands, config))
    assert driver.errors == [], driver.errors[:3]
    # stacks always equal buy-ins less cash-outs, plus nothing: chips never appear or vanish
    assert set(totals) <= {0}, totals[:10]


def test_nlh_hands_play_through_cleanly():
    _run(60)


def test_plo_double_board_hands_play_through_cleanly():
    _run(40, variant="plo4", boards=2)


def test_bomb_pot_hands_play_through_cleanly():
    _run(40, bomb=True, boards=2, variant="plo4", ante=10)
