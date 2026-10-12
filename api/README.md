# api

The network face of the table. It owns no rules: those live in `engine/`.

```
engine/table.py      the rules (pure Python: no network, no clock)
engine/equity.py     win % and outs
api/runtime.py       joins the engine to sockets; maps messages to engine calls
api/hub.py           the connected dealer and overlay sockets
api/main.py          FastAPI app: WebSocket + REST endpoints
api/config.py        settings, from environment variables
api/storage.py       game summaries on disk
api/driver.py        simulated sensors (a stand-in for the RFID/CV bridge)
```

## Run

```bash
python -m api                      # settings from api/config.py
POKER_SIM=0 python -m api          # without the built-in simulator
SIM_SPEED=0.3 python -m api        # simulated hands, faster
```

| Endpoint | |
|---|---|
| `WS /ws/dealer` | state snapshots out, dealer commands in |
| `WS /ws/overlay` | ordered overlay events out |
| `WS /ws/events` | observed sensor events in |
| `GET /api/state`, `/api/games`, `/api/games/<id>.csv`, `/health` | |

See `docs/NETWORKING.md` for how these connect and what to research.

## Observed events (`/ws/events`)

```json
{"type": "cards",  "seat": 3, "cards": ["Ah", "Kh"]}
{"type": "blind",  "seat": 1, "amount": 1}
{"type": "action", "seat": 3, "action": "raise", "to": 6}
{"type": "board",  "boards": [["As", "Kd", "7c"]]}
```

`action` is `fold | check | call | bet | raise | all_in`; `to` is the player's
total in front this street. Every event gets `{"ok": true|false, "error"?, "version"}`.
The engine's `awaiting` field (in each dealer snapshot) says what it needs next.

## Dealer commands (`/ws/dealer`)

`deal_hand`, `showdown`, `next_hand`, `set_config`, `edit_name`, `adjust_stack`,
`remove_player`, `add_player`, `seat_returning`, `new_game`.

## Tests

```bash
pipenv run pytest                              # engine rules + simulated hands
python scripts/smoke_network.py ws://localhost:8000    # needs the server running
```
