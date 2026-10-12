# How the pieces talk to each other

> Where each piece runs (local, homelab, AWS) and how to start them is in
> [`deploy/README.md`](../deploy/README.md).

This is the network side of the table, written as a map of what to read up on.
Everything here runs fine on one laptop; it also works split across machines
(a homelab server, an iPad, an OBS box) with only configuration changes.

## The picture

```
 RFID readers / camera              iPad (Safari)              OBS Browser Source
 (ESP32 nodes, CV process)          dealer UI                  stream overlay
        │                              │  ▲                        ▲
        │ MQTT (planned)               │  │ WebSocket              │ WebSocket
        ▼                              ▼  │ /ws/dealer             │ /ws/overlay
 ┌──────────────┐  WebSocket  ┌─────────────────────────────────────────────┐
 │ sensor bridge│────────────▶│  API process  (FastAPI + uvicorn, port 8000)│
 │ (or sim)     │ /ws/events  │                                             │
 └──────────────┘             │   Runtime ──▶ Table (the rules engine)      │
                              │   • no network, no timers inside the engine │
                              └─────────────────────────────────────────────┘
                                          │ files
                                          ▼
                              engine/data/games/*.json|csv   (summaries)
```

Three kinds of client connect to one server, each over its own WebSocket:

| Client | URL | Direction | What flows |
|---|---|---|---|
| Dealer UI | `/ws/dealer` | both | server → UI: a full **state snapshot** after every change. UI → server: **commands** (`showdown`, `next_hand`, `add_player`, ...) |
| Stream overlay | `/ws/overlay` | server → overlay | an ordered **event script** (`hand_start`, `cards`, `blind`, `turn`, `action`, `street`, `equity`, `next_hand`) |
| Sensors / test tools | `/ws/events` | both | sensor → server: **observed events** (`cards`, `blind`, `action`, `board`). Server replies `{ok, error?, version}` to each |

Plus plain HTTP for things that aren't live: `GET /api/games`, `GET /api/state`,
`GET /health`, and static files (`/overlay/`).

## Why these choices

**WebSocket for the live parts.** HTTP is request/response: the browser asks,
the server answers. The server cannot speak first. A WebSocket starts as an
HTTP request (`Upgrade: websocket`), then stays open as a two-way pipe, so the
server can push a change the instant it happens and the UI never polls.

**Snapshot for the dealer, event script for the overlay.** The dealer UI wants
"what is true now": if it reconnects it just takes the newest snapshot. The
overlay is an animation; it needs "what happened, in order" so it can play it.
Both are the same engine state seen two ways.

**The engine knows nothing about the network.** `engine/table.py` only has
methods (`act`, `register_cards`, ...) and callbacks. `api/runtime.py` is the
only place that joins it to sockets. That is why tests can play hundreds of
hands with no server, and why MQTT, WebSocket, or HTTP could all feed it.

**One writer.** Only the API process changes table state, on a single event
loop, so there are no locks and no two clients can disagree about the order of
things. Clients ask; the server decides.

## What the server guarantees

- **Ordering.** Overlay events go out through one queue, in the order the
  engine produced them. Dealer snapshots are *coalesced*: if three changes land
  at once, only the newest snapshot is sent, because older ones are already
  stale.
- **Late joiners.** A new overlay gets the current hand's events replayed; a
  new dealer UI gets a snapshot immediately.
- **Refusal without damage.** An out-of-turn or illegal input returns an error
  and changes nothing.

## Addresses, ports, and who can reach what

| Thing | Default | Notes |
|---|---|---|
| API (HTTP + WebSocket) | `:8000` | one port serves both; WebSockets are just upgraded HTTP |
| Dealer UI dev server (Vite) | `:5173` | only in development; proxies `/api` and `/ws` to `:8000` |
| MQTT broker (planned) | `:1883` / `:8883` TLS | from the sensor nodes |

- **Listening address.** `0.0.0.0` means "every network interface", so other
  devices can connect. `127.0.0.1` means "this machine only". Set with
  `POKER_HOST`.
- **Finding the server from the iPad.** Use the Mac's LAN IP, or its
  `.local` name (mDNS/Bonjour). A DHCP reservation on the router keeps the IP
  from changing.
- **Same origin.** In development the UI is loaded from `:5173` and talks to
  `/ws/dealer` on that same address; Vite forwards it to `:8000`. The browser
  sees one origin, so there is no CORS to configure. In production a reverse
  proxy (nginx, Caddy) does the same job.

## Security knobs (all in `api/config.py`, set by environment variable)

| Variable | What it does |
|---|---|
| `POKER_ALLOWED_ORIGINS` | Which page origins may use the API. `*` = any. Enforced by CORS for REST, and by an explicit `Origin` check for WebSockets (CORS does not cover WebSockets). |
| `POKER_API_TOKEN` | If set, every REST call and WebSocket must carry `?token=...`. |
| `POKER_HOST` | Bind to `127.0.0.1` to make the API unreachable from the network. |

The overlay endpoint carries hole cards, so treat it as private. The dealer
snapshots deliberately never contain hole cards until showdown.

## Keeping connections alive

- **Pings.** uvicorn sends a WebSocket ping every `POKER_WS_PING` seconds and
  drops a peer that doesn't answer within `POKER_WS_PING_TIMEOUT`. This detects
  a pulled cable or a sleeping iPad.
- **Reconnects.** The dealer UI and overlay reconnect with exponential backoff
  (0.5 s up to 5 s) and the dealer UI reconnects immediately when the iPad
  wakes. After reconnecting, a snapshot brings it fully up to date.
- **Sensors** wait for the reply (`version`) and for the matching snapshot
  before sending the next event, so they never act on stale state.

## Things worth reading up on

1. **HTTP upgrade and WebSocket handshake** (RFC 6455): the `Upgrade`,
   `Connection`, `Sec-WebSocket-Key` headers; frames; close codes (the server
   uses 1008 "policy violation" to refuse).
2. **Same-origin policy and CORS**; why WebSockets need their own `Origin`
   check.
3. **Reverse proxies and WebSockets**: nginx needs
   `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`
   and a long `proxy_read_timeout`. Caddy handles it by default.
4. **TLS (`wss://`)**: a browser page served over `https://` may only open
   `wss://`. Look at Caddy (automatic certificates), `mkcert` for a local CA,
   or Let's Encrypt with a DNS challenge for a homelab domain.
5. **LAN basics**: DHCP reservations, mDNS/Bonjour (`.local`), why `.local`
   doesn't cross VLANs, firewall rules (macOS, `ufw`).
6. **VLANs and segmentation**: put sensors on an IoT VLAN, allow them to reach
   only the API/broker port.
7. **MQTT**: topics, QoS, retained messages, last will; the planned
   RFID → MQTT → API bridge.
8. **Backpressure and ordering** in asyncio: why the overlay uses a queue and
   the dealer UI uses "latest wins".
9. **Containerising**: `docker compose` with the API, an nginx front end, and
   Mosquitto on one bridge network.

## A minimal nginx front end (for a server deployment)

```nginx
server {
    listen 80;
    server_name table.home.lan;

    # the built dealer UI
    root /srv/poker/web/dealer/dist;
    location / { try_files $uri /index.html; }

    # REST and WebSockets go to the API
    location /api/ { proxy_pass http://127.0.0.1:8000; }
    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }
}
```

## Trying it

```bash
POKER_SIM=0 python -m api                 # the server, with no built-in simulator
python scripts/smoke_network.py ws://localhost:8000
```

`smoke_network.py` plays as a dealer, an overlay, and a sensor at once, over
real WebSockets, and prints what each one saw. Point it at
`ws://<server-ip>:8000` from another machine to test a network path.
