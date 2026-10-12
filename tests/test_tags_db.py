import pytest

from engine.rfid.enroll import Quit, Skip, enroll_cards, enroll_chips
from engine.rfid.tags_db import (
    ALL_CARDS, DuplicateCard, DuplicateUid, TagDB, normalize_uid,
)


@pytest.fixture
def db():
    d = TagDB(":memory:")
    yield d
    d.close()


class Scripted:
    """A Source that returns pre-set UID lists, then quits."""

    def __init__(self, *reads):
        self.reads = list(reads)

    def read(self, prompt):
        if not self.reads:
            raise Quit
        item = self.reads.pop(0)
        if item == "skip":
            raise Skip
        return item


def uid(n: int) -> str:
    return f"E0:04:01:50:00:00:00:{n:02X}"


def test_normalize_variants():
    expected = "E0:04:01:50:8A:3C:12:9F"
    assert normalize_uid("e0-04-01-50-8a-3c-12-9f") == expected
    assert normalize_uid("E00401508A3C129F") == expected
    assert normalize_uid(" e0 04 01 50 8a 3c 12 9f ") == expected


def test_normalize_flips_reversed_iso15693():
    assert normalize_uid("9F:12:3C:8A:50:01:04:E0") == "E0:04:01:50:8A:3C:12:9F"


def test_normalize_keeps_14443a_order():
    assert normalize_uid("04:a2:3b:1c:5e:80:00") == "04:A2:3B:1C:5E:80:00"


@pytest.mark.parametrize("bad", ["", "xyz", "E0:04:0", "E0:04"])
def test_normalize_rejects_bad(bad):
    with pytest.raises(ValueError):
        normalize_uid(bad)


def test_add_and_lookup_card(db):
    db.add_card(uid(1), "As", "main")
    assert db.card_map("main") == {uid(1): "As"}
    assert db.get(uid(1).lower()).card == "As"


def test_duplicate_uid_rejected(db):
    db.add_card(uid(1), "As", "main")
    with pytest.raises(DuplicateUid):
        db.add_card(uid(1), "Kd", "main")


def test_same_card_twice_in_one_deck_rejected(db):
    db.add_card(uid(1), "As", "main")
    with pytest.raises(DuplicateCard):
        db.add_card(uid(2), "As", "main")


def test_same_card_allowed_in_different_decks(db):
    db.add_card(uid(1), "As", "main")
    db.add_card(uid(2), "As", "spare")
    assert len(db.card_map()) == 2


def test_invalid_card_rejected(db):
    with pytest.raises(ValueError):
        db.add_card(uid(1), "1x", "main")


def test_chips_and_counts(db):
    for n in range(3):
        db.add_chip(uid(n), 25, "chips")
    db.add_chip(uid(10), 100, "chips")
    assert db.chip_counts() == {25: 3, 100: 1}
    assert db.chip_map()[uid(10)] == 100


def test_missing_cards(db):
    db.add_card(uid(1), "As", "main")
    missing = db.missing_cards("main")
    assert "As" not in missing
    assert len(missing) == 51


def test_export_import_roundtrip(db, tmp_path):
    db.add_card(uid(1), "As", "main")
    db.add_chip(uid(2), 25, "chips")
    path = tmp_path / "tags.json"
    assert db.export_json(path) == 2

    other = TagDB(":memory:")
    assert other.import_json(path) == 2
    assert other.card_map() == db.card_map()
    assert other.chip_map() == db.chip_map()


def test_enroll_cards_flow(db):
    source = Scripted([uid(1)], [uid(2)], [uid(3)])
    n = enroll_cards(db, source, "main", only=["As", "Kd", "Qh"])
    assert n == 3
    assert db.card_map("main") == {uid(1): "As", uid(2): "Kd", uid(3): "Qh"}


def test_enroll_cards_retries_on_multiple_tags(db):
    source = Scripted([uid(1), uid(2)], [uid(1)])
    enroll_cards(db, source, "main", only=["As"])
    assert db.card_map("main") == {uid(1): "As"}


def test_enroll_cards_ignores_same_tag_as_previous(db):
    source = Scripted([uid(1)], [uid(1)], [uid(2)])
    enroll_cards(db, source, "main", only=["As", "Kd"])
    assert db.card_map("main") == {uid(1): "As", uid(2): "Kd"}


def test_enroll_cards_skips_already_enrolled(db):
    db.add_card(uid(1), "As", "main")
    source = Scripted([uid(2)])
    enroll_cards(db, source, "main", only=["As", "Kd"])
    assert db.card_map("main") == {uid(1): "As", uid(2): "Kd"}


def test_enroll_cards_skip_command(db):
    source = Scripted("skip", [uid(1)])
    enroll_cards(db, source, "main", only=["As", "Kd"])
    assert db.card_map("main") == {uid(1): "Kd"}


def test_enroll_chips_batch_respects_count(db):
    source = Scripted([uid(i) for i in range(5)], [uid(i) for i in range(5, 10)])
    n = enroll_chips(db, source, 25, "chips", count=7, batch=True)
    assert n == 7
    assert db.chip_counts() == {25: 7}


def test_all_cards_is_a_full_deck():
    assert len(ALL_CARDS) == 52 and len(set(ALL_CARDS)) == 52
