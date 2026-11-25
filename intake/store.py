from dataclasses import dataclass
import sqlite3

from intake.identity import identify_piece, same_piece
from intake.receipts import IntakeReceipt, decode_intake_receipt, encode_intake_receipt, make_intake_receipt
from issue.envelope import IssuedEnvelope, decode_envelope
from ledger import record_id, write_transaction


@dataclass(frozen=True, slots=True)
class AcceptedPiece:
    intake_id: int
    envelope: IssuedEnvelope
    receipt: IntakeReceipt


class IntakeStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS accepted_pieces (
            intake_id INTEGER PRIMARY KEY,
            site TEXT NOT NULL,
            issue_id INTEGER NOT NULL,
            raw BLOB NOT NULL,
            UNIQUE(site, issue_id)
        )''')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS intake_receipts (
            intake_id INTEGER PRIMARY KEY REFERENCES accepted_pieces(intake_id),
            receipt_json TEXT NOT NULL
        )''')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS intake_conflicts (
            conflict_id INTEGER PRIMARY KEY,
            first_intake_id INTEGER NOT NULL REFERENCES accepted_pieces(intake_id),
            incoming_revision_id INTEGER NOT NULL,
            incoming_body_sha256 TEXT NOT NULL,
            incoming_raw BLOB NOT NULL
        )''')

    def accept_or_register_conflict(self, envelope: IssuedEnvelope) -> AcceptedPiece | None:
        identity = identify_piece(envelope)
        with write_transaction(self.connection):
            row = self.connection.execute('''SELECT intake_id FROM accepted_pieces
                WHERE site = ? AND issue_id = ?''', (identity.site, identity.issue_id)).fetchone()
            if row is None:
                result = self._insert_first(envelope)
            else:
                first = self.read(row[0])
                if same_piece(first.envelope, envelope):
                    result = first
                else:
                    self.connection.execute('''INSERT INTO intake_conflicts(
                        first_intake_id, incoming_revision_id, incoming_body_sha256, incoming_raw
                    ) VALUES (?, ?, ?, ?)''', (first.intake_id, envelope.revision_id,
                                               envelope.body_sha256, envelope.raw))
                    result = None
        return result

    def _insert_first(self, envelope: IssuedEnvelope) -> AcceptedPiece:
        cursor = self.connection.execute('''INSERT INTO accepted_pieces(site, issue_id, raw)
            VALUES (?, ?, ?)''', (envelope.site, envelope.issue_id, envelope.raw))
        intake_id = cursor.lastrowid
        receipt = make_intake_receipt(intake_id, envelope)
        self.connection.execute('''INSERT INTO intake_receipts(intake_id, receipt_json)
            VALUES (?, ?)''', (intake_id, encode_intake_receipt(receipt)))
        return AcceptedPiece(intake_id, envelope, receipt)

    def read(self, intake_id: int) -> AcceptedPiece:
        row = self.connection.execute('''SELECT p.raw, r.receipt_json
            FROM accepted_pieces AS p JOIN intake_receipts AS r USING(intake_id)
            WHERE p.intake_id = ?''', (record_id(intake_id),)).fetchone()
        if row is None:
            raise KeyError(intake_id)
        return AcceptedPiece(intake_id, decode_envelope(row[0]), decode_intake_receipt(row[1]))
