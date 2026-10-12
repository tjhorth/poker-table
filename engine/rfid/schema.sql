-- UID -> physical object lookup for RFID/NFC cards and chips.
-- UIDs are stored normalized: uppercase hex bytes, colon separated, MSB first
-- (ISO15693 UIDs therefore start with E0).

CREATE TABLE IF NOT EXISTS tags (
    uid         TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('card', 'chip')),
    card        TEXT CHECK (card IS NULL OR card GLOB '[2-9TJQKA][cdhs]'),
    denom       INTEGER CHECK (denom IS NULL OR denom > 0),
    set_id      TEXT NOT NULL DEFAULT 'default',   -- which deck or chip set
    enrolled_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    note        TEXT,
    CHECK (
        (kind = 'card' AND card IS NOT NULL AND denom IS NULL) OR
        (kind = 'chip' AND denom IS NOT NULL AND card IS NULL)
    )
);

-- A given card (e.g. 'As') exists once per deck.
CREATE UNIQUE INDEX IF NOT EXISTS ux_tags_card_per_set
    ON tags (set_id, card) WHERE kind = 'card';

CREATE INDEX IF NOT EXISTS ix_tags_kind ON tags (kind);
