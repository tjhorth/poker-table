"""The rules engine, driven only through observed events and dealer commands."""

import pytest

from engine.table import Table


def make_table(stacks, **config):
    """A table with players in seats 1..n; the first hand starts when seated."""
    t = Table(summary_sink=lambda s: "saved.json")
    t.overlay: list[dict] = []
    t.on_overlay.append(t.overlay.append)
    names = ["Ann", "Bob", "Cy", "Di", "Ed", "Flo", "Gus", "Hal"]
    if config:
        assert t.set_config(config) is None
    for i, stack in enumerate(stacks, start=1):
        assert t.add_player(i, names[i - 1], stack) is None
    if len(stacks) >= 2:
        assert t.deal_hand() is None            # the dealer starts play
    return t


HOLES = {  # distinct hole cards for up to 8 NLH players
    1: ["As", "Ad"], 2: ["Kh", "Kd"], 3: ["Qs", "Qd"], 4: ["Jh", "Jd"],
    5: ["Ts", "Td"], 6: ["9h", "9d"], 7: ["8s", "8d"], 8: ["7h", "7d"],
}
PLO_HOLES = {
    1: ["As", "Ad", "Kc", "Qc"], 2: ["Kh", "Kd", "Jc", "Tc"], 3: ["Qs", "Qd", "9c", "8c"],
    4: ["Jh", "Jd", "7c", "6c"],
}
FLOP, TURN, RIVER = ["2c", "5d", "9s"], ["2c", "5d", "9s", "3h"], ["2c", "5d", "9s", "3h", "4h"]


def deal(t, holes=None):
    holes = holes or (HOLES if t.config["variant"] == "nlh" else PLO_HOLES)
    for seat in t.order:
        assert t.register_cards(seat, holes[seat]) is None, seat


def post_blinds(t):
    if t.bomb:
        for seat in list(t.order):
            assert t.post_blind(seat, min(t.config["ante"], t.stack[seat])) is None
        return
    (sb, _, sb_amt), (bb, _, bb_amt) = t.blind_plan
    assert t.post_blind(sb, min(sb_amt, t.stack[sb])) is None
    assert t.post_blind(bb, min(bb_amt, t.stack[bb])) is None


def start(t, holes=None):
    deal(t, holes)
    post_blinds(t)


def act(t, seat, action, to=None):
    err = t.act(seat, action, to)
    assert err is None, err


def board(t, cards, n_boards=1):
    err = t.register_board([cards] * 1 if n_boards == 1 else cards)
    assert err is None, err


def event_types(t):
    return [e["type"] for e in t.overlay]


# -------------------------------------------------------------------- flow

def test_play_starts_only_when_the_dealer_deals():
    t = make_table([200])
    assert t.phase == "waiting" and "need" in t.deal_hand()
    assert t.add_player(2, "Bob", 200) is None
    assert t.phase == "waiting" and t.snapshot()["canDeal"]      # seating alone does not start play
    assert t.add_player(3, "Cy", 200) is None                    # more can still sit down
    assert t.deal_hand() is None
    assert t.phase == "dealing" and t.hand == 1 and t.order == [1, 2, 3]
    assert event_types(t) == ["hand_start"]
    assert "already" in t.deal_hand()


def test_blinds_and_first_to_act_three_handed():
    t = make_table([200, 200, 200])
    # button is seat 8, so seat 1 is the small blind
    assert t.order == [1, 2, 3]
    start(t)
    assert t.phase == "betting"
    assert t.to_act == 3                       # under the gun = left of the big blind
    assert t.in_street == {1: 1, 2: 2}
    assert t.legal()["toCall"] == 2 and t.legal()["minRaiseTo"] == 4


def test_heads_up_button_is_small_blind_and_acts_first_preflop():
    t = make_table([200, 200])
    assert t.button == 2 and t.order == [2, 1]  # seat 2 is the button and the small blind
    start(t)
    assert t.to_act == 2
    act(t, 2, "call", None)
    assert t.to_act == 1                       # big blind has the option
    act(t, 1, "check")
    assert t.phase == "awaiting_board"
    board(t, FLOP)
    assert t.to_act == 1                       # big blind acts first after the flop


def test_big_blind_option_then_flop():
    t = make_table([200, 200, 200])
    start(t)
    act(t, 3, "call")
    act(t, 1, "call")
    assert t.to_act == 2 and t.legal()["canCheck"]
    act(t, 2, "check")
    assert t.phase == "awaiting_board" and t.awaiting()["street"] == "flop"
    board(t, FLOP)
    assert t.phase == "betting" and t.to_act == 1   # small blind first postflop


def test_full_hand_to_showdown_and_payout():
    t = make_table([200, 200, 200])
    start(t)
    act(t, 3, "raise", 6)
    act(t, 1, "fold")
    act(t, 2, "call")
    board(t, FLOP)
    act(t, 2, "check"); act(t, 3, "bet", 10); act(t, 2, "call")
    board(t, TURN)
    act(t, 2, "check"); act(t, 3, "check")
    board(t, RIVER)
    act(t, 2, "check"); act(t, 3, "check")
    assert t.phase == "showdown_ready"
    assert t.showdown() is None
    res = t.result
    assert res["contested"]
    # seat 2 holds KK, seat 3 holds QQ on a 2-5-9-3-4 board: kings win
    assert [p["seat"] for p in res["players"] if p["result"] == "win"] == [2]
    assert sum(p["won"] for p in res["players"]) == sum(p["amount"] for p in res["pots"]) == 1 + 16 + 16
    assert t.stack[2] == 200 - 16 + 33 and t.stack[3] == 200 - 16 and t.stack[1] == 199


def test_next_hand_moves_button_and_starts_the_next_hand():
    t = make_table([200, 200, 200])
    start(t)
    act(t, 3, "fold"); act(t, 1, "fold")
    assert t.phase == "showdown_ready" and t.snapshot()["uncontested"]
    assert t.showdown() is None
    assert t.result["contested"] is False and t.result["players"][0]["seat"] == 2
    assert t.next_hand() is None
    assert t.hand == 2 and t.phase == "dealing"
    assert t.button == 1 and t.order == [2, 3, 1]
    assert event_types(t)[-2:] == ["next_hand", "hand_start"]


# ------------------------------------------------------------------- rules

def test_out_of_turn_and_illegal_actions_are_refused():
    t = make_table([200, 200, 200])
    start(t)
    assert "turn" in t.act(1, "call")                     # not seat 1's turn
    assert "cannot check" in t.act(3, "check")            # faces the big blind
    assert "minimum raise" in t.act(3, "raise", 3)
    assert "already a bet" in t.act(3, "bet", 10)
    assert t.to_act == 3                                  # nothing changed
    act(t, 3, "raise", 8)
    assert "minimum raise" in t.act(1, "raise", 10)       # raise was 6, so to at least 14
    act(t, 1, "raise", 14)


def test_pot_limit_caps_the_raise():
    t = make_table([500, 500, 500], variant="plo4")
    start(t)
    # pot is 3, call is 2: the most UTG can make it is 2 + (3 + 2) = to 7
    assert t.legal()["potLimit"] and t.legal()["maxRaiseTo"] == 7
    assert "pot limit" in t.act(3, "raise", 8)
    act(t, 3, "raise", 7)


def test_short_stack_all_in_does_not_need_a_full_raise():
    t = make_table([200, 200, 7])
    start(t)
    act(t, 3, "all_in")                                   # 7 total: raise of 5 < big blind? still legal
    assert t.in_street[3] == 7 and 3 in t.all_in
    assert t.current_bet == 7


def test_all_in_side_pots_and_uncalled_bet():
    t = make_table([50, 150, 300])
    start(t)
    act(t, 3, "all_in")                                   # 300
    act(t, 1, "all_in")                                   # 50
    act(t, 2, "all_in")                                   # 150
    assert t.phase == "awaiting_board"
    pots = t.pots()
    assert [(p["amount"], p["eligible"]) for p in pots] == [(150, [1, 2, 3]), (200, [2, 3]), (150, [3])]
    board(t, FLOP); board(t, TURN); board(t, RIVER)
    assert t.phase == "showdown_ready"
    t.showdown()
    labels = [p["label"] for p in t.result["pots"]]
    assert labels == ["Main Pot", "Side Pot 1", "Uncalled bet returned"]
    assert sum(p["won"] for p in t.result["players"]) == 500
    # seat 1 has the aces, so they win the main pot but not the side pots
    assert t.stack[1] == 150 and t.stack[2] == 200 and t.stack[3] == 150


def test_everyone_all_in_runs_the_board_without_betting():
    t = make_table([100, 100, 100])
    start(t)
    act(t, 3, "all_in"); act(t, 1, "all_in"); act(t, 2, "all_in")
    for street in ([FLOP], [TURN], [RIVER]):
        assert t.phase == "awaiting_board" and t.to_act is None
        board(t, street[0])
    assert t.phase == "showdown_ready"


def test_bomb_pot_skips_preflop_betting():
    t = make_table([200, 200, 200], bomb=True, ante=10)
    assert t.bomb
    assert t.awaiting()["kind"] == "cards"
    start(t)
    assert t.phase == "awaiting_board" and t.awaiting()["street"] == "flop"
    assert t.pots()[0]["amount"] == 30
    board(t, FLOP)
    assert t.phase == "betting" and t.to_act == 1


def test_double_board_pays_each_board_separately():
    t = make_table([200, 200], boards=2)
    start(t)
    act(t, 2, "all_in"); act(t, 1, "call")
    # seat 1: AA; seat 2: KK. Board 1 gives seat 2 a set of kings; board 2 gives seat 1 a set of aces
    b1 = ["Kc", "7d", "2h"]
    b2 = ["Ac", "8d", "3h"]
    assert t.register_board([b1, b2]) is None
    assert t.register_board([b1 + ["4s"], b2 + ["5c"]]) is None
    assert t.register_board([b1 + ["4s", "6c"], b2 + ["5c", "6d"]]) is None
    t.showdown()
    won = {p["seat"]: p["won"] for p in t.result["players"]}
    assert won == {1: 200, 2: 200}                       # half the pot each
    assert len(t.result["boards"]) == 2


def test_bad_inputs_are_refused_without_changing_state():
    t = make_table([200, 200, 200])
    assert "dealing" in t.register_board([FLOP]) or "No board" in t.register_board([FLOP])
    assert t.register_cards(1, ["As"]) is not None                       # wrong count
    assert t.register_cards(1, ["As", "As"]) is not None                 # duplicate
    assert t.register_cards(1, HOLES[1]) is None
    assert "already registered" in t.register_cards(2, ["As", "Kd"])     # card in use
    assert "not in this hand" in t.register_cards(7, HOLES[7])
    assert "Expected" in t.post_blind(2, 2) or "comes from" in t.post_blind(2, 2)
    assert "is $1" in t.post_blind(1, 5)


# ------------------------------------------------------- seats and ledger

def test_ledger_net_stays_consistent_through_leave_and_return():
    t = make_table([200, 200, 200])
    start(t)
    act(t, 3, "fold"); act(t, 1, "fold")
    t.showdown()                                        # the big blind (seat 2) wins the 3 in the pot
    assert t.stack[2] == 201
    assert t.remove_player(2) is None
    assert t.names[2] is None
    entry = t.inactive[0]
    assert entry["name"] == "Bob" and entry["stack"] == 201 and entry["hands"] == 1
    assert t.seat_returning(2, entry["id"], 301) is None   # comes back with 100 more
    assert t.buy_in[2] == 300 and t.cashed_out[2] == 0
    net = t.stack[2] + t.cashed_out[2] - t.buy_in[2]
    assert net == 1                                        # up the one chip, same as when they left


def test_stack_changes_only_between_hands():
    t = make_table([200, 200, 200])
    assert "between hands" in t.adjust_stack(1, 50)
    start(t)
    assert "between hands" in t.remove_player(1)
    act(t, 3, "fold"); act(t, 1, "fold"); t.showdown()
    assert t.adjust_stack(1, 50) is None and t.buy_in[1] == 250
    assert t.adjust_stack(1, -20) is None and t.cashed_out[1] == 20
    assert "only has" in t.adjust_stack(1, -10_000)


def test_config_changes_apply_to_the_next_hand_only():
    t = make_table([200, 200, 200])
    assert t.set_config({"variant": "plo4", "boards": 2, "sb": 5, "bb": 10}) is None
    assert t.pending and t.config["variant"] == "nlh"
    start(t)
    act(t, 3, "fold"); act(t, 1, "fold"); t.showdown()
    t.next_hand()
    assert t.config["variant"] == "plo4" and t.config["boards"] == 2 and t.pending is None
    assert t.overlay[-1]["hole_cards"] == 4 and t.overlay[-1]["game"] == "2brd PLO"
    assert t.blinds == "5/10"


def test_new_game_saves_a_summary_and_clears_the_table():
    saved = []
    t = make_table([200, 200, 200])
    t.summary_sink = lambda s: saved.append(s) or "game.json"
    start(t)
    act(t, 3, "fold"); act(t, 1, "fold"); t.showdown()
    assert t.new_game() is None
    summary = saved[0]
    assert summary["handsPlayed"] == 1
    assert {p["name"]: p["handsPlayed"] for p in summary["players"]} == {"Ann": 1, "Bob": 1, "Cy": 1}
    assert summary["totals"]["net"] == 0
    assert t.seated() == [] and t.hand == 0 and t.phase == "waiting"
    assert t.overlay[-1] == {"type": "next_hand", "winners": []}
    assert t.last_summary["file"] == "game.json"


def test_snapshot_never_contains_hole_cards_before_showdown():
    t = make_table([200, 200, 200])
    start(t)
    snap = t.snapshot()
    assert all(isinstance(p["cards"], int) for p in snap["players"])
    assert "Ah" not in str(snap) and "As" not in str(snap)
