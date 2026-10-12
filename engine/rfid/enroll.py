"""Interactive enrollment of RFID/NFC cards and chips into the UID table.

Run from the repo root, for example:

    pipenv run python -m engine.rfid.enroll --source stdin cards --set-id main
    pipenv run python -m engine.rfid.enroll --source mqtt  chips --denom 25 --batch
    pipenv run python -m engine.rfid.enroll status

Sources:
    stdin     type or paste UIDs (from a phone NFC app, a USB reader, a log)
    mqtt      read UID sets published by a reader node (see --topic)
    simulate  random UIDs, for a dry run with no hardware
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import random
import sys
import time
from typing import Protocol

from .tags_db import (
    ALL_CARDS, DEFAULT_DB, DEFAULT_EXPORT, DuplicateCard, DuplicateUid,
    TagDB, card_name, normalize_uid,
)


class Quit(Exception):
    pass


class Skip(Exception):
    pass


class Source(Protocol):
    def read(self, prompt: str) -> list[str]:
        """Block until a set of UIDs is available. Raise Quit or Skip as needed."""


# ---------------------------------------------------------------- sources

class StdinSource:
    """One line per read: UIDs separated by spaces or commas. 's' skips, 'q' quits."""

    def read(self, prompt: str) -> list[str]:
        print(prompt)
        while True:
            try:
                line = input("  uid> ").strip()
            except EOFError:
                raise Quit
            if line.lower() in ("q", "quit"):
                raise Quit
            if line.lower() in ("s", "skip"):
                raise Skip
            if not line:
                continue
            try:
                return [normalize_uid(p) for p in line.replace(",", " ").split()]
            except ValueError as e:
                print(f"  {e}")


class SimulateSource:
    def __init__(self, per_read: int = 1, seed: int | None = None):
        self.per_read = per_read
        self.rng = random.Random(seed)

    def read(self, prompt: str) -> list[str]:
        print(prompt)
        uids = []
        for _ in range(self.per_read):
            body = bytes([0xE0, 0x04] + [self.rng.randrange(256) for _ in range(6)])
            uids.append(":".join(f"{b:02X}" for b in body))
        print(f"  simulated: {' '.join(uids)}")
        return uids


class MqttSource:
    """Waits for a stable, non-empty UID set that differs from the previous one."""

    def __init__(self, host: str, port: int, topic: str, user: str | None,
                 password: str | None, stable: int = 3, timeout: float = 120.0):
        import paho.mqtt.client as mqtt

        self.topic, self.stable, self.timeout = topic, stable, timeout
        self.q: queue.Queue[list[str]] = queue.Queue()
        self.last: tuple[str, ...] = ()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if user:
            self.client.username_pw_set(user, password)
        self.client.on_connect = lambda c, *_: c.subscribe(topic)
        self.client.on_message = self._on_message
        self.client.connect(host, port)
        self.client.loop_start()

    def _on_message(self, _client, _userdata, msg) -> None:
        try:
            uids = [normalize_uid(u) for u in json.loads(msg.payload)["uids"]]
        except (ValueError, KeyError, TypeError):
            return
        self.q.put(sorted(set(uids)))

    def read(self, prompt: str) -> list[str]:
        print(prompt)
        deadline = time.monotonic() + self.timeout
        streak: list[str] | None = None
        count = 0
        while time.monotonic() < deadline:
            try:
                uids = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            if not uids or tuple(uids) == self.last:
                streak, count = None, 0
                continue
            if uids == streak:
                count += 1
            else:
                streak, count = uids, 1
            if count >= self.stable:
                self.last = tuple(uids)
                return uids
        raise Quit

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()


# ---------------------------------------------------------------- flows

def enroll_cards(db: TagDB, source: Source, set_id: str, redo: bool = False,
                 only: list[str] | None = None) -> int:
    targets = only or ALL_CARDS
    pending = [c for c in targets if redo or c not in db.enrolled_cards(set_id)]
    if not pending:
        print(f"All requested cards are already enrolled in set {set_id!r}.")
        return 0

    done, last_uid = 0, None
    for i, card in enumerate(pending, 1):
        while True:
            try:
                uids = source.read(f"[{i}/{len(pending)}] Place the {card_name(card)} ({card}) alone on the reader")
            except Skip:
                print(f"  skipped {card}")
                break
            except Quit:
                print(f"Stopped. Enrolled {done} card(s) this session.")
                return done
            if len(uids) != 1:
                print(f"  expected exactly 1 tag, saw {len(uids)}. Remove the others.")
                continue
            uid = uids[0]
            if uid == last_uid:
                print("  same tag as the previous card. Swap cards and try again.")
                continue
            try:
                db.add_card(uid, card, set_id, overwrite=redo)
            except (DuplicateUid, DuplicateCard) as e:
                print(f"  {e}")
                continue
            print(f"  enrolled {uid} -> {card}")
            last_uid = uid
            done += 1
            break
    print(f"Done. Enrolled {done} card(s). Missing in {set_id!r}: {db.missing_cards(set_id) or 'none'}")
    return done


def enroll_chips(db: TagDB, source: Source, denom: int, set_id: str,
                 count: int | None, batch: bool) -> int:
    enrolled = 0
    while count is None or enrolled < count:
        remaining = "" if count is None else f", {count - enrolled} to go"
        what = "one or more chips" if batch else "one chip"
        try:
            uids = source.read(f"Place {what} (${denom}) on the reader{remaining}. 'q' to finish")
        except (Skip, Quit):
            break
        if not batch and len(uids) != 1:
            print(f"  expected exactly 1 tag, saw {len(uids)}.")
            continue
        new = 0
        for uid in uids:
            if count is not None and enrolled >= count:
                break
            try:
                db.add_chip(uid, denom, set_id)
            except DuplicateUid as e:
                print(f"  skipping: {e}")
                continue
            enrolled += 1
            new += 1
        print(f"  +{new} new (${denom} total this session: {enrolled})")
    print(f"Done. Enrolled {enrolled} ${denom} chip(s).")
    return enrolled


def print_status(db: TagDB, set_id: str | None) -> None:
    sets = sorted({t.set_id for t in db.all()}) if set_id is None else [set_id]
    if not sets:
        print("No tags enrolled yet.")
        return
    for s in sets:
        cards = db.enrolled_cards(s)
        chips = db.chip_counts(s)
        print(f"set {s!r}:", end="")
        if cards or not chips:
            print(f" cards {len(cards)}/52", end="")
            missing = db.missing_cards(s)
            if cards and missing:
                print(f"  missing: {' '.join(missing)}", end="")
        if chips:
            print("  chips: " + ", ".join(f"${d} x{n}" for d, n in chips.items()), end="")
        print()


def print_list(db: TagDB) -> None:
    for t in db.all():
        what = t.card if t.kind == "card" else f"${t.denom}"
        print(f"{t.uid:<26} {t.kind:<5} {what:<5} {t.set_id}")


# ---------------------------------------------------------------- CLI

def build_source(args: argparse.Namespace) -> Source:
    if args.source == "stdin":
        return StdinSource()
    if args.source == "simulate":
        return SimulateSource(per_read=getattr(args, "sim_batch", 1))
    return MqttSource(
        host=os.environ.get("MQTT_HOST", "localhost"),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        topic=args.topic,
        user=os.environ.get("MQTT_USER"),
        password=os.environ.get("MQTT_PASSWORD"),
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="enroll", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite file")
    p.add_argument("--source", choices=["stdin", "mqtt", "simulate"], default="stdin")
    p.add_argument("--topic", default="poker/table1/enroll/tags", help="MQTT topic (mqtt source)")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("cards", help="enroll a 52-card deck")
    c.add_argument("--set-id", default="default", help="deck name, e.g. 'main'")
    c.add_argument("--redo", action="store_true", help="re-enroll cards that already exist")
    c.add_argument("--only", nargs="+", metavar="CARD", help="just these cards, e.g. As Kd")

    ch = sub.add_parser("chips", help="enroll chips of one denomination")
    ch.add_argument("--denom", type=int, required=True)
    ch.add_argument("--set-id", default="default")
    ch.add_argument("--count", type=int, help="stop after this many")
    ch.add_argument("--batch", action="store_true", help="accept many chips per read")

    s = sub.add_parser("status", help="show what's enrolled / missing")
    s.add_argument("--set-id")
    sub.add_parser("list", help="list every enrolled tag")
    e = sub.add_parser("export", help="write the table to JSON")
    e.add_argument("path", nargs="?", default=str(DEFAULT_EXPORT))
    i = sub.add_parser("import", help="load a JSON export (upserts)")
    i.add_argument("path", nargs="?", default=str(DEFAULT_EXPORT))
    r = sub.add_parser("remove", help="delete one tag by UID")
    r.add_argument("uid")

    args = p.parse_args(argv)
    db = TagDB(args.db)
    try:
        if args.cmd == "status":
            print_status(db, args.set_id)
        elif args.cmd == "list":
            print_list(db)
        elif args.cmd == "export":
            print(f"exported {db.export_json(args.path)} tag(s) to {args.path}")
        elif args.cmd == "import":
            print(f"imported {db.import_json(args.path)} tag(s) from {args.path}")
        elif args.cmd == "remove":
            print("removed" if db.remove(args.uid) else "not found")
        else:
            source = build_source(args)
            try:
                if args.cmd == "cards":
                    enroll_cards(db, source, args.set_id, args.redo, args.only)
                else:
                    enroll_chips(db, source, args.denom, args.set_id, args.count, args.batch)
            except KeyboardInterrupt:
                print("\nInterrupted.")
            finally:
                if hasattr(source, "close"):
                    source.close()
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
