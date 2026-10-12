"""Settings for the API process, read from environment variables.

Nothing here is secret by default. Change them at the shell:

    POKER_PORT=9000 POKER_ALLOWED_ORIGINS=http://192.168.1.50:5173 python -m api
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    # where the server listens. 0.0.0.0 = every network interface (reachable
    # from other devices on the LAN); 127.0.0.1 = this machine only.
    host: str = os.environ.get("POKER_HOST", "0.0.0.0")
    port: int = int(os.environ.get("POKER_PORT", "8000"))

    # Browser origins allowed to call the REST API and open WebSockets.
    # "*" accepts any (fine on a trusted LAN); otherwise a comma list such as
    # "http://192.168.1.50:5173,http://tablet.local:5173".
    allowed_origins: list[str] = field(
        default_factory=lambda: _list(os.environ.get("POKER_ALLOWED_ORIGINS", "*"))
    )

    # If set, every WebSocket and REST call must carry ?token=<value>.
    token: str = os.environ.get("POKER_API_TOKEN", "")

    # where game summaries are written
    games_dir: Path = Path(os.environ.get("POKER_GAMES_DIR", REPO / "engine" / "data" / "games"))

    # the built-in simulated sensors (see api/driver.py)
    sim: bool = os.environ.get("POKER_SIM", "1") == "1"
    sim_speed: float = float(os.environ.get("SIM_SPEED", "1"))
    sim_seed_players: bool = os.environ.get("POKER_SIM_SEED", "1") == "1"

    # seconds between WebSocket pings; a dead connection is dropped when a
    # ping goes unanswered for ws_ping_timeout seconds
    ws_ping_interval: float = float(os.environ.get("POKER_WS_PING", "20"))
    ws_ping_timeout: float = float(os.environ.get("POKER_WS_PING_TIMEOUT", "20"))


settings = Settings()
