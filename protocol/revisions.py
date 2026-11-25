from dataclasses import dataclass
import json
import sqlite3

from ledger import record_id, write_transaction
from protocol.catalog import CodeCatalog, build_catalog, require_text
from protocol.transitions import TransitionGraph, transition_from_record, transition_to_record
from protocol.validation import validate_revision


@dataclass(frozen=True, slots=True)
class FrozenRevision:
    revision_id: int
    protocol_id: str
    device_id: str
    catalog: CodeCatalog
    graph: TransitionGraph


class RevisionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def initialize(self) -> None:
        self.connection.execute('''CREATE TABLE IF NOT EXISTS revisions (
            revision_id INTEGER PRIMARY KEY,
            protocol_id TEXT NOT NULL,
            device_id TEXT NOT NULL,
            snapshot_json TEXT NOT NULL
        )''')
        self.connection.execute('''CREATE INDEX IF NOT EXISTS revisions_protocol
            ON revisions(protocol_id, revision_id)''')

    def load(self, revision_id: int) -> FrozenRevision:
        row = self.connection.execute('''SELECT protocol_id, device_id, snapshot_json
            FROM revisions WHERE revision_id = ?''', (record_id(revision_id),)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        protocol_id, device_id, text = row
        snapshot = json.loads(text)
        graph = TransitionGraph(
            tuple(snapshot['states']), snapshot['initial'],
            tuple(transition_from_record(edge) for edge in snapshot['transitions']),
        )
        return FrozenRevision(revision_id, protocol_id, device_id, build_catalog(snapshot['catalog']), graph)


def seal_revision(store: RevisionStore, protocol_id: str, catalog: CodeCatalog,
                  graph: TransitionGraph, *, device_id: str) -> int:
    require_text(protocol_id, 'protocol number')
    require_text(device_id, 'device number')
    validate_revision(catalog, graph)
    snapshot = json.dumps({
        'catalog': dict(catalog.entries), 'states': graph.states, 'initial': graph.initial,
        'transitions': [transition_to_record(edge) for edge in graph.transitions],
    }, ensure_ascii=False, separators=(',', ':'))
    with write_transaction(store.connection):
        cursor = store.connection.execute('''INSERT INTO revisions(protocol_id, device_id, snapshot_json)
            VALUES (?, ?, ?)''', (protocol_id, device_id, snapshot))
        revision_id = cursor.lastrowid
    return revision_id
