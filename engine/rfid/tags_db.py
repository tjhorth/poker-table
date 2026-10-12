"""UID -> card/chip lookup, backed by SQLite."""

from __future__ import annotations

import json
import os
import re
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

RANKS = "AKQJT98765432"
SUITS = "shdc"
ALL_CARDS = [r + s for s in SUITS for r in RANKS]

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB = Path(
    os.environ.get(
        "POKER_TAGS_DB",
        Path(__file__).resolve().parents[1] / "data" / "tags.sqlite3",
    )
)
DEFAULT_EXPORT = DEFAULT_DB.with_name("tags.json")

_NON_HEX = re.compile(r"[^0-9A-Fa-f]")
_VALID_UID_LENGTHS = (4, 7, 8, 10)

_RANK_NAMES = {
    "A": "Ace", "K": "King", "Q": "Queen", "J": "Jack", "T": "Ten",
    "9": "Nine", "8": "Eight", "7": "Seven", "6": "Six", "5": "Five",
    "4": "Four", "3": "Three", "2": "Two",
}
_SUIT_NAMES = {"s": "spades", "h": "hearts", "d": "diamonds", "c": "clubs"}


class TagError(Exception):
    """Base class for tag database problems."""


class DuplicateUid(TagError):
    pass


class DuplicateCard(TagError):
    pass


def card_name(card: str) -> str:
    return f"{_RANK_NAMES[card[0]]} of {_SUIT_NAMES[card[1]]}"


def normalize_uid(raw: str) -> str:
    """Return a canonical UID string, e.g. 'E0:04:01:50:8A:3C:12:9F'.

    Accepts any separator or none, and any case. ISO15693 UIDs are 8 bytes and
    begin with 0xE0 when written MSB first; some libraries report them
    reversed, so an 8-byte UID that ends in E0 (and doesn't start with it) is
    flipped.
    """
    cleaned = _NON_HEX.sub("", raw)
    if not cleaned or len(cleaned) % 2:
        raise ValueError(f"not a valid UID: {raw!r}")
    data = bytes.fromhex(cleaned)
    if len(data) not in _VALID_UID_LENGTHS:
        raise ValueError(f"unexpected UID length {len(data)} bytes: {raw!r}")
    if len(data) == 8 and data[0] != 0xE0 and data[-1] == 0xE0:
        data = data[::-1]
    return ":".join(f"{b:02X}" for b in data)


@dataclass(frozen=True)
class Tag:
    uid: str
    kind: str
    card: str | None
    denom: int | None
    set_id: str
    enrolled_at: str
    note: str | None


class TagDB:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA_PATH.read_text())

    def close(self) -> None:
        self.conn.close()

    # -- writes ---------------------------------------------------------

    def add_card(self, uid: str, card: str, set_id: str = "default",
                 note: str | None = None, overwrite: bool = False) -> Tag:
        uid = normalize_uid(uid)
        if card not in ALL_CARDS:
            raise ValueError(f"unknown card {card!r}")
        self._check_conflicts(uid, set_id, card, overwrite)
        self.conn.execute(
            "INSERT OR REPLACE INTO tags (uid, kind, card, denom, set_id, note) "
            "VALUES (?, 'card', ?, NULL, ?, ?)",
            (uid, card, set_id, note),
        )
        self.conn.commit()
        return self.get(uid)

    def add_chip(self, uid: str, denom: int, set_id: str = "default",
                 note: str | None = None, overwrite: bool = False) -> Tag:
        uid = normalize_uid(uid)
        if denom <= 0:
            raise ValueError("denomination must be positive")
        if self.get(uid) and not overwrite:
            raise DuplicateUid(f"{uid} is already enrolled")
        self.conn.execute(
            "INSERT OR REPLACE INTO tags (uid, kind, card, denom, set_id, note) "
            "VALUES (?, 'chip', NULL, ?, ?, ?)",
            (uid, denom, set_id, note),
        )
        self.conn.commit()
        return self.get(uid)

    def remove(self, uid: str) -> bool:
        cur = self.conn.execute("DELETE FROM tags WHERE uid = ?", (normalize_uid(uid),))
        self.conn.commit()
        return cur.rowcount > 0

    def _check_conflicts(self, uid: str, set_id: str, card: str, overwrite: bool) -> None:
        existing = self.get(uid)
        if existing and not overwrite:
            raise DuplicateUid(f"{uid} is already enrolled as {self.describe(existing)}")
        holder = self.conn.execute(
            "SELECT uid FROM tags WHERE kind='card' AND set_id=? AND card=?",
            (set_id, card),
        ).fetchone()
        if holder and holder["uid"] != uid:
            if not overwrite:
                raise DuplicateCard(
                    f"{card} in set {set_id!r} is already enrolled as {holder['uid']}"
                )
            self.conn.execute("DELETE FROM tags WHERE uid = ?", (holder["uid"],))

    # -- reads ----------------------------------------------------------

    def get(self, uid: str) -> Tag | None:
        row = self.conn.execute(
            "SELECT * FROM tags WHERE uid = ?", (normalize_uid(uid),)
        ).fetchone()
        return Tag(**dict(row)) if row else None

    def all(self) -> list[Tag]:
        rows = self.conn.execute(
            "SELECT * FROM tags ORDER BY kind, set_id, card, denom, uid"
        ).fetchall()
        return [Tag(**dict(r)) for r in rows]

    def card_map(self, set_id: str | None = None) -> dict[str, str]:
        sql = "SELECT uid, card FROM tags WHERE kind='card'"
        args: tuple = ()
        if set_id is not None:
            sql += " AND set_id = ?"
            args = (set_id,)
        return {r["uid"]: r["card"] for r in self.conn.execute(sql, args)}

    def chip_map(self, set_id: str | None = None) -> dict[str, int]:
        sql = "SELECT uid, denom FROM tags WHERE kind='chip'"
        args: tuple = ()
        if set_id is not None:
            sql += " AND set_id = ?"
            args = (set_id,)
        return {r["uid"]: r["denom"] for r in self.conn.execute(sql, args)}

    def enrolled_cards(self, set_id: str) -> set[str]:
        return set(self.card_map(set_id).values())

    def missing_cards(self, set_id: str) -> list[str]:
        have = self.enrolled_cards(set_id)
        return [c for c in ALL_CARDS if c not in have]

    def chip_counts(self, set_id: str | None = None) -> dict[int, int]:
        counts: dict[int, int] = {}
        for denom in self.chip_map(set_id).values():
            counts[denom] = counts.get(denom, 0) + 1
        return dict(sorted(counts.items()))

    @staticmethod
    def describe(tag: Tag) -> str:
        if tag.kind == "card":
            return f"{tag.card} ({tag.set_id})"
        return f"${tag.denom} chip ({tag.set_id})"

    # -- import / export ------------------------------------------------

    def export_json(self, path: str | Path = DEFAULT_EXPORT) -> int:
        tags = [asdict(t) for t in self.all()]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps({"version": 1, "tags": tags}, indent=2) + "\n")
        return len(tags)

    def import_json(self, path: str | Path = DEFAULT_EXPORT) -> int:
        data = json.loads(Path(path).read_text())
        n = 0
        for t in data["tags"]:
            if t["kind"] == "card":
                self.add_card(t["uid"], t["card"], t.get("set_id", "default"),
                              t.get("note"), overwrite=True)
            else:
                self.add_chip(t["uid"], t["denom"], t.get("set_id", "default"),
                              t.get("note"), overwrite=True)
            n += 1
        return n
