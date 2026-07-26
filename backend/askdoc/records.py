"""Durable answer records, so a verified answer can be shared and re-checked.

IDEA_SCOPE §3 M4 calls the answer record "a shareable proof artifact". Until
now it was neither shareable nor durable: it lived in the browser tab and died
with it. This is the storage that makes the claim true.

Two properties do the work:

* **A record is immutable.** It is written once, at the moment verification
  ruled, and never updated. An answer whose provenance could be edited
  afterwards is not proof of anything.

* **The citation is stored as offsets, not as text.** Opening a shared record
  re-slices `doc.text[quote_start:quote_end]` exactly as the live path does, so
  the link proves the same thing the original screen did rather than
  reproducing a copy of it. If the two ever disagreed we would rather show the
  document than the record.

sqlite3 from the stdlib on purpose -- a new service dependency during a
buildathon is a demo that does not start.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from pathlib import Path

from .config import CACHE_DIR
from .models import AnswerRecord

DB_PATH = CACHE_DIR / "records.db"

# Long enough that a share link cannot be found by guessing. A record carries
# the document it was asked of, and an uploaded page may be someone's own
# paperwork -- an enumerable id would hand those out.
ID_BYTES = 12

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_records (
    record_id  TEXT PRIMARY KEY,
    doc_id     TEXT NOT NULL,
    asked_at   TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS answer_records_doc ON answer_records (doc_id);
"""


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.executescript(_SCHEMA)
    return connection


def save(record: AnswerRecord) -> str:
    """Store a record and return the id a share link is built from.

    The whole record is kept as JSON rather than shredded into columns: it is
    written once and read whole, and a schema that has to be migrated in step
    with `AnswerRecord` is a way for a shared link to start lying.
    """
    record_id = secrets.token_urlsafe(ID_BYTES)
    with _connect() as connection:
        connection.execute(
            "INSERT INTO answer_records (record_id, doc_id, asked_at, payload)"
            " VALUES (?, ?, ?, ?)",
            (record_id, record.doc_id, record.asked_at, record.model_dump_json()),
        )
    return record_id


def load(record_id: str) -> AnswerRecord | None:
    """The record behind a share link, or None if there is no such link."""
    if not record_id:
        return None
    with _connect() as connection:
        row = connection.execute(
            "SELECT payload FROM answer_records WHERE record_id = ?", (record_id,)
        ).fetchone()
    if row is None:
        return None
    return AnswerRecord.model_validate(json.loads(row[0]))


def count() -> int:
    """How many records are stored. For the health endpoint and tests."""
    with _connect() as connection:
        return connection.execute("SELECT COUNT(*) FROM answer_records").fetchone()[0]
