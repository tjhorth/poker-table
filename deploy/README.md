# Running the table: local, homelab, and AWS

One set of container images, three places to run them, one command to choose:

```bash
./poker up local        # everything on this machine (development, testing)
./poker up homelab      # the home server: engine, MQTT, dealer UI, TLS
./poker up aws          # the stream relay on EC2
```

Nothing about the code changes between them. What changes is *which services
run where* and *how they find each other*, and that lives in small files in
`deploy/`.

---

## 1. Where each piece runs

| Piece | Runs on | Why |
|---|---|---|
| **Game engine + API** | **Homelab** | Sensors send inputs every ~150 ms. Keeping the engine on the same LAN means a game never depends on the internet. |
| **MQTT broker** | **Homelab** | The RFID/ESP32 nodes publish to it. Same reason. |
| **MQTT bridge** (planned) | **Homelab** | Reads MQTT, writes to the engine. Sits next to both. |
| **Equity / outs compute** | **Homelab** (inside the engine process) | See section 5. |
| **Dealer UI** | Homelab by default; **S3 + CloudFront** is supported | See section 6. |
| **Stream relay (MediaMTX)** | **AWS EC2** | Home sends one stream; AWS fans it out to viewers. Your home IP and upload speed stay out of it. |
| **Viewer page + invite links** | **AWS** | Public, but private by invitation. |
| **Game summaries, backups** | **S3 bucket** | Cheap, off-site. |
| **OBS + cameras** | At the table | Hardware-bound. |

```
   TABLE (home)                      HOMELAB                          AWS
 ┌────────────────┐        ┌───────────────────────────┐      ┌───────────────────────┐
 │ RFID readers   │  MQTT  │ Mosquitto ─▶ MQTT bridge  │      │ EC2 (t4g.small)       │
 │ (ESP32)        │───────▶│                  │        │      │  Caddy ─▶ MediaMTX    │
 │ cameras        │        │                  ▼        │      │      ▲                │
 └────────────────┘        │       Engine + API ◀──────┼──┐   │      │ HLS            │
                           │        │   │   │          │  │   │   viewers (invite)    │
 iPad (dealer UI) ─────────┼────────┘   │   │ WS       │  │   └───────────▲───────────┘
                           │            │   └─▶ overlay│  │               │ RTMP
 OBS (overlay + video) ────┼────────────┘              │  │               │
        │                  └───────────────────────────┘  │               │
        └─────────────────────────────────────────────────┴───────────────┘
        (one 4 Mbps stream to AWS)                        game summaries ──▶ S3
```

---

## 2. The three environments

| | local | homelab | aws |
|---|---|---|---|
| **Compose file** | `compose/local.yml` | `compose/homelab.yml` | `compose/aws.yml` |
| **Env file** | `env/local.env` | `env/homelab.env` | `env/aws.env` |
| **Services** | api, ui, caddy, mosquitto, mediamtx | api, ui, caddy, mosquitto (+ mediamtx with `--profile relay`) | mediamtx, caddy |
| **Sensors** | simulated (`POKER_SIM=1`) | real (`POKER_SIM=0`) | n/a |
| **TLS** | none (http) | Caddy internal CA, or Let's Encrypt | Let's Encrypt |
| **Auth** | none | `POKER_API_TOKEN` | OBS publish password, viewer login |
| **MQTT** | anonymous | passwords + ACL (`infra/mosquitto/config`) | n/a |

### local

```bash
./poker up local
```

| What | Where |
|---|---|
| Dealer UI | http://localhost:8080 |
| API (direct) | http://localhost:8000 |
| Overlay page | http://localhost:8080/overlay/index.html?ws=ws://localhost:8080/ws/overlay |
| MQTT broker | `localhost:1883` (no password) |
| Relay: publish | `rtmp://localhost:1935/live` (stream key `table1`) |
| Relay: watch | http://localhost:8888/live/table1 |

For hot-reload UI development, run `cd web/dealer && npm run dev` instead of
using the `ui` container; Vite proxies `/api` and `/ws` to `:8000`.

### homelab

1. **Env file.** `./poker up homelab` creates `deploy/env/homelab.env` and stops
   so you can edit it: `SITE_ADDRESS`, `POKER_API_TOKEN` (`openssl rand -hex 24`),
   `POKER_ALLOWED_ORIGINS`.
2. **MQTT passwords.** `infra/mosquitto/config/passwd` and `acl` are used as
   they are (see the notes in `infra/mosquitto`); the `passwd` file is not in git.
3. **Start it** on the server. Either log in and run `./poker up homelab`
   there, or from your laptop with a Docker context (see "Running it remotely").
4. **DNS.** Make `table.home.lan` resolve to the server (router DNS entry, or a
   DHCP reservation plus a hosts entry).
5. **Trust the certificate.** With `CADDY_TLS=internal`, Caddy signs with its
   own private CA. Export its root cert once and install it on the iPad:
   `./poker exec homelab caddy cat /data/caddy/pki/authorities/local/root.crt`.
   (A real domain removes this step; see section 8.)

Only Caddy (80/443) and MQTT (1883) are published. The API is reachable only
through Caddy, on the Docker network.

### aws (the relay)

Runs on the EC2 instance. Terraform (section 9) creates the instance; then:

```bash
docker context create aws --docker "host=ssh://ec2-user@<elastic-ip>"
POKER_CONTEXT=aws ./poker up aws
```

Edit `deploy/mediamtx/mediamtx.aws.yml` first (publish and viewing passwords).
Images are built *on the instance*, so ARM (Graviton) is handled natively.

---

## 3. What is in this folder

```
deploy/
  README.md                   this file
  compose/
    common.yml                service definitions shared by every environment
    local.yml  homelab.yml  aws.yml
  docker/
    api.Dockerfile            engine + API (python:3.12-slim, non-root, healthcheck)
    api.requirements.txt      pinned dependencies
    ui.Dockerfile             builds the dealer UI, serves it with nginx
    nginx-ui.conf
  caddy/
    Caddyfile.local  Caddyfile.homelab  Caddyfile.aws
  mosquitto/local.conf        anonymous broker for development
  mediamtx/mediamtx.local.yml mediamtx.aws.yml
  env/*.env.example           copy to *.env (gitignored) and edit
poker                         the wrapper script
```

**How the compose files fit together.** `common.yml` holds each service once.
Each environment file lists only the services it runs and pulls them in with
`extends`, then adds ports, volumes and settings specific to that place.
Running `./poker config <env>` prints the merged result.

**Volumes.**

| Volume | Holds |
|---|---|
| `poker-data` | game summaries (`/data/games`) and the tag database |
| `mosquitto-data` | retained MQTT messages |
| `caddy-data` | TLS certificates (keep it: losing it re-issues certs) |

---

## 4. The MQTT bridge

**What it is.** The readers speak MQTT: an ESP32 publishes "I currently see
these tag UIDs" many times a second. The engine speaks its own events: "seat 3's
hole cards are A♥ K♥", "seat 4 raised to 20". The bridge is the small program
that translates one into the other.

```
ESP32 ──MQTT──▶ Mosquitto ──▶  BRIDGE  ──WebSocket /ws/events──▶ Engine
 poker/table1/seat3/cards     (debounce, map UID→card,              ▲
 poker/table1/seat3/bet        total chips, decide event)           │ state, "awaiting"
                                   ▲                                │
                                   └──────────── /ws/dealer ────────┘
```

**How it works, step by step.**

1. **Subscribe** to `poker/table1/#`.
2. **Normalize** each UID (case, byte order) with the same `normalize_uid` the
   enrollment tool uses.
3. **Debounce.** Raw reads flicker. A set of UIDs counts as real only after it
   has been identical for N scans (the enrollment tool uses 3), and an empty
   set means "nothing on the reader".
4. **Translate** with the tag database (`engine/rfid/tags_db.py`):
   - hole-card zone: two or four UIDs become card codes → a `cards` event;
   - bet zone: chip UIDs become a dollar total.
5. **Use context.** The bridge also listens to the engine's state. The engine's
   `awaiting` field says exactly which input it is waiting for ("the big blind
   from seat 2", "an action from seat 4, to call $6"), so the bridge decides what
   a new bet-zone total means: it equals the call, so `call`; it is more, so
   `raise`; and so on.
6. **Send** the event to `/ws/events`. The engine either accepts it or replies
   with an error ("out of turn", "below the minimum raise"), which the bridge
   can surface to the dealer.

**What it can't do alone.** Check and fold leave nothing in a bet zone, so
they need another signal: a button per seat, a gesture seen by the camera, or a
"confirm" on the dealer screen (the "propose and confirm" flow).

**Where it runs.** A container on the homelab next to Mosquitto and the
engine. It is not built yet; the engine's `/ws/events` interface is ready for it.

---

## 5. Equity and outs: homelab, and what AWS would look like

Equity is a short CPU burst (about a second on a mini PC) done off the event
loop in a worker thread, so it never blocks the table. At your size there is
nothing to gain from moving it, and a cost: the hole cards would leave your
house.

If you ever did move it, the seam already exists: the engine calls
`on_equity(request)` with the hands and board, and `Runtime._compute_equity`
answers. In AWS that would look like:

```
engine ──HTTPS (TLS, signed)──▶ Lambda Function URL  (equity.py + pokerkit, arm64)
        ◀── {equities, outs} ──
```

| | Homelab (now) | AWS Lambda |
|---|---|---|
| Latency | ~0.3–1 s compute | + 30–80 ms round trip, + cold start of 1–3 s |
| Cost | $0 | well under $1/month at this volume |
| Failure mode | none extra | the internet; needs a fallback |
| Privacy | hole cards stay home | hole cards sent to AWS |

Recommendation: keep it local.

---

## 6. The dealer UI on S3 + CloudFront

It works, but you should know what it needs, because the UI then lives on a
different origin from the API:

| Requirement | Why |
|---|---|
| The API must be reachable with **`wss://` and a certificate the iPad trusts** | A page loaded over `https://` may only open secure WebSockets |
| `POKER_ALLOWED_ORIGINS` includes the CloudFront hostname | The API checks the page's `Origin` |
| The UI needs the API address at runtime (a small `config.json`) | Today it uses same-origin paths (`/ws/dealer`), which only work when something proxies them |
| The token is passed as `?token=` | Already supported |

That is a modest amount of extra setup compared with serving the UI from the
homelab, where none of it is needed and the dealer screen keeps working with
the internet down. A good split is:

- **Dealer UI:** served by the homelab (already done in `homelab.yml`).
- **Viewer page** (the page friends open from an invite link): S3 + CloudFront,
  because it has no engine dependency and benefits from being public and cheap.

Terraform will create the bucket and distribution either way (section 9), so
you can switch the dealer UI over later once the domain and certificate exist.

---

## 7. The stream relay and private invite links

**Why AWS for the relay.** OBS sends one stream (about 4 Mbps) to the relay;
the relay serves every viewer. That means no ports open on your home network,
your home IP stays private, and 20 viewers cost you the same home upload as 1.

**Private by invitation.** Two stages:

1. **Now (in `mediamtx.aws.yml`)**: OBS publishes with a password; viewing needs
   a login. Simple, but everyone shares one credential.
2. **Invite links (planned)**: each invite is a *signed, expiring token*.
   `./poker invite --name Sam --days 7` would print
   `https://watch.example.com/?t=<token>`. The relay validates the token on
   every request, so you can revoke or expire one person without changing
   anyone else's. MediaMTX can validate JWTs or call an HTTP auth endpoint;
   check the docs for the version you run.

OBS settings: Server `rtmp://<relay-ip>:1935/live`, key `table1`, user `obs`
with the publish password. Restrict port 1935 in the security group to your
home IP.

---

## 8. Domain, Tailscale, and WireGuard

### A domain name

You don't have one yet; buy one. It is the single thing that makes real HTTPS,
CloudFront aliases, and invite links possible.

| Where | About | Note |
|---|---|---|
| **Route 53** | ~$13–15/yr for `.com`, plus $0.50/mo hosted zone | One place for domain and DNS; works naturally with Terraform |
| **Cloudflare Registrar** | at-cost, ~$10–11/yr for `.com` | Cheapest; DNS lives at Cloudflare |

Suggested names under one domain: `stream.` (relay), `watch.` (viewer page),
`table.` (homelab, via Tailscale or LAN).

### WireGuard

A modern VPN protocol: a fast, small, encrypted tunnel between machines. You
generate a key pair on each, list each other's public keys and addresses, pick a
UDP port, and traffic flows. It is excellent for learning because nothing is
hidden, but **you manage everything**: keys, addresses, routes, and what happens
when a device is behind NAT.

### Tailscale

A service built **on top of WireGuard** that does the managing for you. Install
it, sign in, and your devices (iPad, laptop, homelab, EC2) can reach each other
by name from anywhere, with no ports opened and no keys exchanged by hand. It
adds NAT traversal, names (MagicDNS), access rules (ACLs), and optional
HTTPS certificates for your device names. The free personal plan is plenty for
this project.

| | WireGuard | Tailscale |
|---|---|---|
| Setup | manual, per pair of peers | install and sign in |
| Learning value | high | lower (it hides the details) |
| NAT / roaming | you handle it | automatic |
| Names, access rules | DIY | built in |

**How you'd use them here:** Tailscale for convenience (reach the dealer UI
from anywhere, SSH to the server, a valid HTTPS name without buying anything);
WireGuard as a weekend project to understand what Tailscale is doing, e.g. a
tunnel between the homelab and the EC2 relay. Viewers don't need either: they
use the public relay with an invite link.

### Your AX6000 router

"AX6000" is a Wi-Fi speed class shared by several models (ASUS RT-AX88U,
TP-Link Archer AX6000, Netgear RAX120, ...), so the answer depends on which you
have. In general:

- **It makes a great access point.** Put it in AP / access-point mode and it
  provides fast Wi-Fi 6 for the iPad and laptop, and a 2.4 GHz network for the
  ESP32 sensors (the ESP32 can't use 5 GHz).
- **It may replace the Wi-Fi AP in the VLAN shopping list.** If its firmware can
  tag an SSID with a VLAN ID (newer ASUS "Guest Network Pro", OpenWrt-capable
  models), you can skip buying an Omada access point (about $60–100).
- **If it can't tag VLANs**, its guest network with client isolation is still a
  usable IoT SSID, just without the VLAN-routing lessons.
- **It's not the router to learn VLANs on**; a router with proper inter-VLAN
  firewalling (ER605, or OPNsense on a mini PC) is better for that.

Tell me the exact model and I'll check what it can do.

---

## 9. AWS: EC2 and Terraform (planned, not yet written)

| Choice | Value |
|---|---|
| Instance | **t4g.small** (2 vCPU ARM Graviton, 2 GiB), about $12/mo if left running |
| OS | Ubuntu 24.04 LTS arm64 (or Amazon Linux 2023) |
| Disk | 20 GB gp3 |
| Address | one Elastic IP |
| Access | **SSM Session Manager**; no SSH port open |
| Security group | 80/443 from anywhere; 1935 from your home IP only |
| Start/stop | a scheduled start/stop, or start it from the CLI for game nights |

Terraform layout (`deploy/terraform/`, to be written):

| Module | Creates |
|---|---|
| `network` | uses the default VPC; security group |
| `relay` | EC2 instance, Elastic IP, instance profile (SSM + S3 backups), user data that installs Docker and starts the stack |
| `storage` | S3 bucket for game summaries and backups (versioned, private, lifecycle rule) |
| `viewer` | S3 bucket + CloudFront distribution (Origin Access Control) for the viewer / dealer UI |
| `dns` | Route 53 records and ACM certificates (CloudFront certs live in us-east-1) |
| `budget` | a $25 budget alarm |

`terraform apply` brings it up, `terraform destroy` removes it, and the compose
file on the instance is the same `aws.yml` described above.

---

## 10. Secrets and configuration

| Secret | Where it lives |
|---|---|
| `POKER_API_TOKEN` | `deploy/env/homelab.env` (gitignored) |
| MQTT passwords | `infra/mosquitto/config/passwd` (gitignored) |
| MediaMTX passwords | `deploy/mediamtx/mediamtx.aws.yml` on the instance; later SSM Parameter Store |
| AWS credentials | an instance profile on EC2; your own SSO login for Terraform |

Never commit `deploy/env/*.env`. The `.example` files are the templates.

---

## 11. Running it remotely

A Docker *context* points the `docker` CLI at another machine over SSH, and
`./poker` honours it:

```bash
docker context create homelab --docker "host=ssh://you@table-server"
POKER_CONTEXT=homelab ./poker up homelab
POKER_CONTEXT=homelab ./poker logs homelab api
```

The build happens on the remote machine, so you never cross-compile.

---

## 12. Troubleshooting

| Symptom | Check |
|---|---|
| `./poker up` complains about env | Edit the file it just created, run it again |
| UI loads but says "Connecting to the table…" | WebSocket is blocked: `./poker logs <env> caddy`; for homelab, did you add `?token=...`? |
| iPad says the certificate is untrusted | Install Caddy's root cert (section 2, homelab step 5), or use a real domain |
| Overlay shows nothing | Open `/overlay/index.html?ws=wss://<host>/ws/overlay&...` and check the token and origin |
| Relay shows no stream | OBS server/key; security group allows 1935 from your IP; `./poker logs aws mediamtx` |
| Sensors can't reach MQTT | The VLAN firewall rule for 1883 |

---

## 13. Built and not built

| | State |
|---|---|
| Images: api, ui | built and tested |
| `./poker up local` | built and tested (UI, WebSockets via the proxy, MQTT, relay with an HLS test stream) |
| `./poker up homelab` | built and tested on one machine (TLS, redirect, token enforcement over `wss://`) |
| `./poker up aws` | files written and validated; not yet run on EC2 |
| MQTT bridge | designed above; not written |
| Invite links | designed above; not written |
| Terraform | designed above; not written |
| S3 backup job | not written |
| UI runtime `config.json` (for S3 + CloudFront) | not written |
