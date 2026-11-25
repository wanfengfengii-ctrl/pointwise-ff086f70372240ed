from dataclasses import dataclass
import json
import sqlite3

from intake.selection import AcceptedPair
from intake.store import AcceptedPiece
from ledger import record_id, write_transaction
from review.length import AgreementStatistics


@dataclass(frozen=True, slots=True)
class ReportParent:
    intake_id: int
    site: str
    issue_id: int
    revision_id: int
    body_sha256: str

    @classmethod
    def from_piece(cls, piece: AcceptedPiece) -> 'ReportParent':
        envelope = piece.envelope
        return cls(piece.intake_id, envelope.site, envelope.issue_id, envelope.revision_id, envelope.body_sha256)


@dataclass(frozen=True, slots=True)
class SignedReport:
    report_id: int
    statistics: AgreementStatistics
    parents: tuple[ReportParent, ReportParent]
    receipt: str


class ReportStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY,
            statistics_json TEXT NOT NULL
        )''')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS report_parents (
            report_id INTEGER NOT NULL REFERENCES reports(report_id),
            position INTEGER NOT NULL CHECK(position IN (0, 1)),
            intake_id INTEGER NOT NULL REFERENCES accepted_pieces(intake_id),
            site TEXT NOT NULL,
            issue_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            body_sha256 TEXT NOT NULL,
            PRIMARY KEY(report_id, position)
        )''')
        self.connection.execute('''CREATE TABLE IF NOT EXISTS report_receipts (
            report_id INTEGER PRIMARY KEY REFERENCES reports(report_id),
            receipt TEXT NOT NULL UNIQUE
        )''')

    def commit_report(self, statistics: AgreementStatistics, pair: AcceptedPair) -> SignedReport:
        parents = (ReportParent.from_piece(pair.left), ReportParent.from_piece(pair.right))
        with write_transaction(self.connection):
            cursor = self.connection.execute('INSERT INTO reports(statistics_json) VALUES (?)',
                                             (json.dumps(statistics.to_record()),))
            report_id = cursor.lastrowid
            self.connection.executemany('''INSERT INTO report_parents(
                report_id, position, intake_id, site, issue_id, revision_id, body_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?)''', [
                (report_id, position, parent.intake_id, parent.site, parent.issue_id,
                 parent.revision_id, parent.body_sha256)
                for position, parent in enumerate(parents)
            ])
            receipt = f'R-{report_id}'
            self.connection.execute('INSERT INTO report_receipts(report_id, receipt) VALUES (?, ?)',
                                    (report_id, receipt))
        return SignedReport(report_id, statistics, parents, receipt)

    def read(self, report_id: int) -> SignedReport:
        row = self.connection.execute('''SELECT r.statistics_json, s.receipt
            FROM reports AS r JOIN report_receipts AS s USING(report_id)
            WHERE r.report_id = ?''', (record_id(report_id),)).fetchone()
        if row is None:
            raise KeyError(report_id)
        statistics, receipt = row
        parents = tuple(ReportParent(*record) for record in self.connection.execute('''
            SELECT intake_id, site, issue_id, revision_id, body_sha256
            FROM report_parents WHERE report_id = ? ORDER BY position''', (report_id,)))
        if len(parents) != 2:
            raise sqlite3.DatabaseError('signed report must have two stored parent positions')
        return SignedReport(report_id, AgreementStatistics.from_record(json.loads(statistics)), parents, receipt)
