# api

FastAPI service that connects the game engine to the dealer UI and the stream
overlay.

| Endpoint | Direction | Purpose |
|---|---|---|
| `WS /ws/dealer` | state snapshots out, commands in | The dealer UI (`web/dealer`) |
| `WS /ws/overlay` | events out | The stream overlay (`web/overlay`) |
| `/overlay/` | static | The overlay page, served for convenience |
| `GET /health` | | Liveness check |

## Run

```bash
cd ~/Desktop/poker
pipenv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

`SIM_SPEED=0.3` makes the simulated table play faster (default `1`).

## The simulated table

`sim.py` stands in for the real game engine: it plays scripted hands (side
pots, PLO, a double-board bomb pot, an uncontested pot) with real random cards
and real hand evaluation from PokerKit. It keeps the contract the real engine
will have, so swapping it out should not touch the UIs:

- **Dealer snapshots** (`TableSim.snapshot`): everything the dealer needs.
  Hole cards are *not* included until showdown.
- **Overlay events**: `hand_start`, `cards`, `blind`, `turn`, `action`,
  `street`, `equity`, `next_hand` (documented at the top of `web/overlay/index.html`).
- **Dealer commands**: `{"cmd": "showdown"}`, `{"cmd": "next_hand"}`,
  `{"cmd": "set_config", "game": "plo4", "blinds": "2/5"}`.

Config changes are queued and applied when the next hand starts.

`equity.py` computes each live player's win chance (enumerated or sampled) and
the "outs" for players who are behind.
