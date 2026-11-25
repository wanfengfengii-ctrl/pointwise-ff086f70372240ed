import sqlite3

from issue.envelope import IssuedEnvelope, decode_envelope, encode_envelope
from ledger import record_id, write_transaction
from protocol.catalog import require_text


class IssueRegister:
    def __init__(self, connection: sqlite3.Connection, site: str):
        self.connection = connection
        self.site = require_text(site, 'issuing site')

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS issued_pieces (
            site TEXT NOT NULL,
            issue_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
            raw BLOB NOT NULL,
            PRIMARY KEY(site, issue_id)
        )''')

    def create(self, revision_id: int, body: bytes) -> IssuedEnvelope:
        record_id(revision_id)
        with write_transaction(self.connection):
            last_id, = self.connection.execute('''SELECT COALESCE(MAX(issue_id), 0)
                FROM issued_pieces WHERE site = ?''', (self.site,)).fetchone()
            issue_id = record_id(last_id + 1)
            raw = encode_envelope(self.site, issue_id, revision_id, body)
            envelope = decode_envelope(raw)
            self.connection.execute('''INSERT INTO issued_pieces(site, issue_id, revision_id, raw)
                VALUES (?, ?, ?, ?)''', (self.site, issue_id, revision_id, raw))
        return envelope

    def read(self, issue_id: int) -> IssuedEnvelope:
        row = self.connection.execute('''SELECT raw FROM issued_pieces
            WHERE site = ? AND issue_id = ?''', (self.site, record_id(issue_id))).fetchone()
        if row is None:
            raise KeyError(issue_id)
        return decode_envelope(row[0])
