import json
import sqlite3

from ledger import record_id, write_transaction
from runs.observations import ObservedRun, SupportStatus, validate_observation


class RunHistory:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS observed_runs (
            run_id INTEGER PRIMARY KEY,
            revision_id INTEGER NOT NULL REFERENCES revisions(revision_id),
            codes_json TEXT NOT NULL,
            support TEXT NOT NULL CHECK(support IN ('supported', 'outside_protocol'))
        )''')
        self.connection.execute('''CREATE INDEX IF NOT EXISTS observed_runs_revision
            ON observed_runs(revision_id, run_id)''')

    def append(self, revision_id: int, codes: tuple[str, ...], status: SupportStatus) -> ObservedRun:
        record_id(revision_id)
        sequence = validate_observation(codes)
        status = SupportStatus(status)
        with write_transaction(self.connection):
            cursor = self.connection.execute('''INSERT INTO observed_runs(revision_id, codes_json, support)
                VALUES (?, ?, ?)''', (revision_id, json.dumps(sequence, ensure_ascii=False), status.value))
            run = ObservedRun(cursor.lastrowid, revision_id, sequence, status)
        return run

    @staticmethod
    def _decode(row) -> ObservedRun:
        run_id, revision_id, codes, status = row
        return ObservedRun(run_id, revision_id, tuple(json.loads(codes)), SupportStatus(status))

    def read(self, run_id: int) -> ObservedRun:
        row = self.connection.execute('''SELECT run_id, revision_id, codes_json, support
            FROM observed_runs WHERE run_id = ?''', (record_id(run_id),)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return self._decode(row)

    def for_revision(self, revision_id: int) -> tuple[ObservedRun, ...]:
        rows = self.connection.execute('''SELECT run_id, revision_id, codes_json, support
            FROM observed_runs WHERE revision_id = ? ORDER BY run_id''', (record_id(revision_id),))
        return tuple(self._decode(row) for row in rows)
