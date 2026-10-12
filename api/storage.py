"""Game summaries on disk: one JSON and one CSV file per finished game."""

from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import REPO, settings


def save_summary(summary: dict[str, Any]) -> str:
    ended = datetime.fromisoformat(summary["endedAt"])
    folder = settings.games_dir
    folder.mkdir(parents=True, exist_ok=True)
    stem = f"game-{ended.strftime('%Y%m%d-%H%M%S')}"
    (folder / f"{stem}.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (folder / f"{stem}.csv").open("w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["player", "hands_played", "bought_in", "cashed_out", "ending_stack", "net"])
        for r in summary["players"]:
            out.writerow([r["name"], r["handsPlayed"], r["buyIn"], r["cashedOut"],
                          r["endingStack"], r["net"]])
    path = folder / f"{stem}.json"
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def recent_games(limit: int = 3) -> list[dict[str, Any]]:
    folder = settings.games_dir
    if not folder.is_dir():
        return []
    games = []
    for f in sorted(folder.glob("game-*.json"), reverse=True)[:limit]:
        try:
            games.append({"id": f.stem, **json.loads(f.read_text())})
        except (OSError, ValueError):
            continue                      # an unreadable or half-written file
    return games


def csv_path(game_id: str) -> Path | None:
    if not re.fullmatch(r"game-\d{8}-\d{6}", game_id):
        return None
    path = settings.games_dir / f"{game_id}.csv"
    return path if path.is_file() else None
