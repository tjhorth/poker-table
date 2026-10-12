# RFID tag enrollment

Every card and chip has an RFID/NFC tag with a factory-set **UID** (unique
identifier). The game engine never reads anything *from* the tags. It only needs
to know which UID belongs to which card or chip. Enrollment builds that lookup
table once, so the engine can turn `E0:04:01:50:8A:3C:12:9F` into `As` or
`$25`.

```
tag on the reader ──▶ reader node ──MQTT──▶ enroll.py ──▶ tags.sqlite3
                       (ESP32 + PN5180)                    (UID -> card / chip)
```

## Files

| File | Purpose |
|---|---|
| `schema.sql` | The `tags` table and its rules |
| `tags_db.py` | Database access: add, look up, export, import, UID normalization |
| `enroll.py` | The interactive enrollment command-line tool |
| `../data/tags.sqlite3` | The database (gitignored) |
| `../data/tags.json` | A committable export of the table (see [Backup](#backup-and-restore)) |

## Before you start

Run everything from the **repo root**, using the project's environment:

```bash
cd ~/Desktop/poker
pipenv run python -m engine.rfid.enroll --help
```

Each tag has a **set** (`--set-id`): a name for the physical deck or chip set it
belongs to, such as `main` or `spare`. The same card (for example `As`) can
exist once in each set, but only once within a set.

## Choosing a source

The tool needs a way to receive UIDs. Pick one with `--source`:

| Source | UIDs come from | Use it when |
|---|---|---|
| `stdin` (default) | You type or paste them | You have no reader node yet, or you're copying UIDs from a phone NFC app, a USB reader, or a log |
| `mqtt` | A reader node publishing to a topic | The ESP32 and PN5180 are running |
| `simulate` | Random generated UIDs | A dry run with no hardware at all |

## Enrolling cards

Enroll a full 52-card deck:

```bash
pipenv run python -m engine.rfid.enroll --source mqtt cards --set-id main
```

The tool walks the deck and asks for one card at a time:

```
[1/52] Place the Ace of spades (As) alone on the reader
  enrolled E0:04:6B:25:9C:E9:F5:A1 -> As
[2/52] Place the King of spades (Ks) alone on the reader
```

Put the named card on the reader, wait for the confirmation line, then swap in
the next card.

### Card options

| Option | Effect |
|---|---|
| `--set-id NAME` | Which deck this is (default `default`) |
| `--only As Kd ...` | Enroll just these cards, for example to fix one |
| `--redo` | Re-enroll cards that are already in the set, replacing the old UID |

### It's resumable

Cards that are already enrolled in the set are skipped. If you stop partway,
run the same command again and it picks up where it left off.

## Enrolling chips

Chips are interchangeable within a denomination, so you enroll by value, not by
individual chip:

```bash
# one chip at a time
pipenv run python -m engine.rfid.enroll --source mqtt chips --denom 25 --set-id chips

# many chips on the reader at once, stop at 40
pipenv run python -m engine.rfid.enroll --source mqtt chips --denom 25 --set-id chips --batch --count 40
```

### Chip options

| Option | Effect |
|---|---|
| `--denom N` | The chip's value (required) |
| `--set-id NAME` | Which chip set (default `default`) |
| `--count N` | Stop after enrolling this many |
| `--batch` | Accept several chips per read, so you can put a stack on the reader and enroll them in one go |

Chips whose UID is already enrolled are skipped with a message, so you can
safely put a stack back on the reader.

## What you can publish (the `mqtt` source)

The enrollment tool subscribes to a topic (default `poker/table1/enroll/tags`,
change it with `--topic`) and reads the set of UIDs currently in the reader's
field. The reader node publishes a JSON message on every scan:

```json
{"v": 1, "ts": 1760000000.12, "uids": ["E0:04:01:50:8A:3C:12:9F"]}
```

Only the `uids` list matters. UIDs are normalized on arrival, so case and
separators don't matter, and byte-reversed ISO15693 UIDs are flipped
automatically.

### What each kind of message means

| What the node publishes | What the tool does |
|---|---|
| **One UID** (`"uids": ["E0:04:..."]`) | After the same set arrives **3 times in a row**, it counts as a read and the tag is enrolled |
| **An empty list** (`"uids": []`) | Treated as "nothing on the reader". It resets the stability counter, so a partial read never counts toward the three identical scans |
| **Several UIDs** | In `cards` mode: rejected with "expected exactly 1 tag, saw N. Remove the others." and the same card is asked for again. In `chips --batch` mode: every new UID is enrolled. |
| **The same set as the last accepted read** | Ignored. You must remove the tag and present a different one. This prevents enrolling one tag as two cards. |
| **A UID already in the database** | Rejected with a message (see [Error messages](#error-messages)), and nothing is written |
| **A malformed message** (not JSON, no `uids` key, a bad UID) | Silently ignored |
| **Nothing for 120 seconds** | The tool gives up and stops cleanly |

In practice, the reader node simply keeps scanning and publishing. Lifting a
tag away and placing the next one is all you do.

### Requirements for the reader node

**1. Publish every scan, not only changes (required).**
A tag is accepted only after the *same* UID set arrives three times in a row
(`MqttSource(stable=3)` in `enroll.py`). A node that publishes only when the
set changes would send each set once, so it would never reach three, and
enrollment would appear to hang. Publish on every scan cycle, even when nothing
changed.

**2. Publish an empty list when the field is empty (recommended).**
Send `{"uids": []}` when no tag is present, rather than staying silent. The
enrollment tool does not strictly need it, since it simply keeps waiting, but an
empty message:

- resets the stability counter, so a partial read followed by nothing never
  counts toward the three identical scans, and
- tells the rest of the system "the field is empty" as a positive statement.
  Silence is ambiguous: it could mean the tag was lifted or the node went
  offline. The game engine will need that distinction for hole cards, so the
  firmware should publish empty sets from the start.

Typical sequence for two cards:

```
{"uids": []}                      # nothing on the reader
{"uids": ["E0:04:..:01"]}         # one card landed (partial read, resets the count)
{"uids": ["E0:04:..:01", "E0:04:..:02"]}   # both visible
{"uids": ["E0:04:..:01", "E0:04:..:02"]}   # identical: 2
{"uids": ["E0:04:..:01", "E0:04:..:02"]}   # identical: 3 -> accepted
```

The time to acceptance is roughly three scan intervals after both tags are
first seen together. The scan interval is a setting in the reader firmware.

### Credentials

The script reads its MQTT settings from environment variables:

| Variable | Default |
|---|---|
| `MQTT_HOST` | `localhost` |
| `MQTT_PORT` | `1883` |
| `MQTT_USER` | none |
| `MQTT_PASSWORD` | none |

The broker's ACL (`infra/mosquitto/config/acl`) controls who may publish to
the enrollment topic. The `engine` user can publish and subscribe anywhere
under `poker/`. A node named `enroll` can publish to `poker/table1/enroll/#`
through the `%u` pattern rule, so create that user for a dedicated enrollment
reader.

### Testing without a reader

Pretend to be the reader node by publishing the same set three times:

```bash
for i in 1 2 3; do
  mosquitto_pub -h localhost -u engine -P '<password>' \
    -t poker/table1/enroll/tags \
    -m '{"v":1,"uids":["E0:04:01:50:00:00:00:01"]}'
done
```

Publish an empty list between tags, like a real reader does when you lift one:

```bash
mosquitto_pub -h localhost -u engine -P '<password>' \
  -t poker/table1/enroll/tags -m '{"v":1,"uids":[]}'
```

## Actions in `stdin` mode

With `--source stdin`, the tool prompts for a line each time:

```
[1/52] Place the Ace of spades (As) alone on the reader
  uid>
```

| You type | Effect |
|---|---|
| A UID (`E0:04:01:50:8A:3C:12:9F`, or without colons, any case) | Enrolls it as the requested card or chip |
| Several UIDs separated by spaces or commas | Treated as several tags in the field (accepted in `chips --batch`, rejected for cards) |
| `s` or `skip` | Skip this card and move to the next |
| `q` or `quit` | Stop. Progress so far is saved. |
| A blank line | Ignored, asks again |
| Something that isn't a valid UID | An error message, and asks again |

## Other commands

| Command | What it does |
|---|---|
| `status` | Show cards enrolled per set (and which are missing) and chip counts per denomination. Add `--set-id NAME` for one set. |
| `list` | Print every enrolled tag |
| `remove UID` | Delete one tag |
| `export [PATH]` | Write the table to JSON (default `engine/data/tags.json`) |
| `import [PATH]` | Load a JSON export, replacing matching tags |

Examples:

```bash
pipenv run python -m engine.rfid.enroll status
pipenv run python -m engine.rfid.enroll list
pipenv run python -m engine.rfid.enroll remove E0:04:01:50:8A:3C:12:9F
```

Use a different database file with `--db PATH`, or set `POKER_TAGS_DB`.

## Error messages

| Message | Cause | What to do |
|---|---|---|
| `expected exactly 1 tag, saw N. Remove the others.` | Several tags in the reader's field while enrolling a card | Take the extra cards or chips away |
| `same tag as the previous card. Swap cards and try again.` | The reader still sees the last card | Lift it off and put the next one on |
| `<UID> is already enrolled as As (main)` | That tag was enrolled before | Use `--redo` to replace it, or use the correct card |
| `<card> in set 'main' is already enrolled as <UID>` | Another tag already holds this card in the set | Check you didn't swap two cards, or use `--redo --only <card>` to replace it |
| `unexpected UID length ...` / `not a valid UID` | Malformed UID text | Check what was typed or published |

## Backup and restore

`tags.sqlite3` is gitignored. Keep a text copy in the repo:

```bash
pipenv run python -m engine.rfid.enroll export    # writes engine/data/tags.json
git add engine/data/tags.json
```

To rebuild the database from that file on another machine:

```bash
pipenv run python -m engine.rfid.enroll import
```

UIDs aren't secrets, so committing the export is fine.

## Using the table in the engine

```python
from engine.rfid.tags_db import TagDB, normalize_uid

db = TagDB()
card_by_uid = db.card_map("main")      # {"E0:04:...": "As", ...}
chip_by_uid = db.chip_map("chips")     # {"E0:04:...": 25, ...}

cards = [card_by_uid[normalize_uid(u)] for u in uids]
```

Load the maps once at startup rather than querying for every scan. Always
normalize UIDs coming from MQTT with `normalize_uid()` before looking them up.

## Tests

```bash
pipenv run pytest tests/test_tags_db.py
```
