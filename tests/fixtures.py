from contextlib import ExitStack, closing
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from intake.receive import receive_piece
from intake.store import IntakeStore
from issue.freeze import issue_revision
from issue.register import IssueRegister
from ledger import open_database
from protocol.catalog import build_catalog
from protocol.revisions import RevisionStore, seal_revision
from protocol.transitions import Transition, TransitionGraph
from review.store import ReportStore
from runs.history import RunHistory


def serial_graph(*codes):
    states = tuple(f'private-{i}' for i in range(len(codes) + 1))
    edges = [Transition(states[i], 'public', 1, states[i + 1], code) for i, code in enumerate(codes)]
    edges.append(Transition(states[-1], 'end', 1))
    return TransitionGraph(states, states[0], tuple(edges))


def seal(connection, graph, *, protocol='diagnostic-1', device='bench-private', catalog=None):
    if catalog is None:
        catalog = {edge.code: f'Catalog entry for {edge.code}' for edge in graph.transitions if edge.code is not None}
    return seal_revision(RevisionStore(connection), protocol, build_catalog(catalog), graph, device_id=device)


def sample_graph(site):
    initial = 'private-start'
    tail = 'private-sampling'
    half = Fraction(1, 2)
    if site == 'A':
        first = Transition(initial, 'end', half)
    else:
        first = Transition(initial, 'public', half, tail, 'X')
    return TransitionGraph((initial, tail), initial, (
        first, Transition(initial, 'silent', half, tail),
        Transition(tail, 'end', half), Transition(tail, 'public', half, tail, 'X'),
    ))


def wire_piece(site, issue_id, revision_id, count, rows, initial=0):
    # This fixture constructs the documented exchange format without the issuing code.
    def order(row):
        state, kind, target, code, weight = row
        return state, kind, -1 if target is None else target, code or '', *weight

    body = json.dumps({'state_count': count, 'initial': initial, 'transitions': sorted(rows, key=order)},
                      ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return json.dumps({'version': 1, 'site': site, 'issue_id': issue_id, 'revision_id': revision_id,
                       'body_sha256': sha256(body.encode('utf-8')).hexdigest(), 'body': body},
                      ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def compliant_pair():
    tail = [[1, 'end', None, None, [1, 2]], [1, 'public', 1, 'X', [1, 2]]]
    silent = [[0, 'silent', 1, None, [1, 2]]]
    left = wire_piece('A', 7, 92, 2, tail + silent + [[0, 'end', None, None, [1, 2]]])
    right = wire_piece('B', 7, 56, 2, tail + silent + [[0, 'public', 1, 'X', [1, 2]]])
    return left, right


def fixture_record_mass(raw, codes):
    # Only used for the two-state witness whose silent edges are acyclic.
    document = json.loads(json.loads(raw)['body'])
    pending = [(document['initial'], 0, Fraction(1))]
    total = Fraction(0)
    while pending:
        current, offset, mass = pending.pop()
        for source, kind, target, code, ratio in document['transitions']:
            if source != current:
                continue
            contribution = mass * Fraction(*ratio)
            if kind == 'end' and offset == len(codes):
                total += contribution
            elif kind == 'silent':
                pending.append((target, offset, contribution))
            elif kind == 'public' and offset < len(codes) and codes[offset] == code:
                pending.append((target, offset + 1, contribution))
    return total


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        self.resources = ExitStack()
        self.addCleanup(self.resources.close)
        self.root = Path(self.resources.enter_context(TemporaryDirectory(prefix='hailan-test-')))

    def station(self, site):
        connection = self.resources.enter_context(closing(open_database(self.root / f'{site}.sqlite')))
        for store in (RevisionStore(connection), RunHistory(connection), IssueRegister(connection, site)):
            store.initialize()
        return connection

    def center(self):
        connection = self.resources.enter_context(closing(open_database(self.root / 'center.sqlite')))
        intake, reports = IntakeStore(connection), ReportStore(connection)
        intake.initialize()
        reports.initialize()
        return connection, intake, reports

    def ship(self, source, site, graph, intake):
        revision_id = seal(source, graph)
        envelope = issue_revision(IssueRegister(source, site), revision_id)
        return receive_piece(intake, envelope.raw)

    def ship_sample_pair(self, intake):
        left, right = (self.station(site) for site in ('A', 'B'))
        a = self.ship(left, 'A', sample_graph('A'), intake)
        b = self.ship(right, 'B', sample_graph('B'), intake)
        left.close()
        right.close()
        return a, b
