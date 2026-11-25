from fractions import Fraction

from protocol.revisions import RevisionStore
from protocol.transitions import Transition, TransitionGraph
from runs.history import RunHistory
from runs.import_run import record_run
from runs.observations import SupportStatus
from tests.fixtures import LedgerTestCase, seal, serial_graph


class RevisionTests(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.source = self.station('A')
        self.revisions = RevisionStore(self.source)
        self.history = RunHistory(self.source)

    def test_freeze_and_log(self):
        revision_id = seal(self.source, serial_graph('X'))
        run = record_run(self.history, revision_id, ['X'])
        self.assertEqual(run.revision_id, revision_id)
        self.assertEqual(run.status, SupportStatus.SUPPORTED)
        self.assertEqual(self.history.read(run.run_id), run)

    def test_revision_snapshot(self):
        original = serial_graph('X')
        correction = serial_graph('Y')
        old = seal(self.source, original, catalog={'X': 'before maintenance'})
        new = seal(self.source, correction, catalog={'Y': 'after maintenance'})
        self.assertNotEqual(old, new)
        self.assertEqual(self.revisions.load(old).catalog.entries, (('X', 'before maintenance'),))
        self.assertEqual(self.revisions.load(new).catalog.entries, (('Y', 'after maintenance'),))
        self.assertEqual(self.revisions.load(old).graph, original)
        self.assertEqual(self.revisions.load(new).graph, correction)
        self.assertEqual(record_run(self.history, old, ['X']).status, SupportStatus.SUPPORTED)
        self.assertEqual(record_run(self.history, new, ['X']).status, SupportStatus.OUTSIDE_PROTOCOL)

    def test_reinitialize(self):
        old = seal(self.source, serial_graph('X'))
        new = seal(self.source, serial_graph('Y'))
        run = record_run(self.history, new, ['Y'])
        self.source.close()
        reopened = self.station('A')
        self.assertEqual(RevisionStore(reopened).load(old).catalog.codes, {'X'})
        self.assertEqual(RevisionStore(reopened).load(new).catalog.codes, {'Y'})
        self.assertEqual(RunHistory(reopened).for_revision(new), (run,))

    def assert_rejected_without_revision(self, graph, message):
        with self.assertRaisesRegex(ValueError, message):
            seal(self.source, graph)
        self.assertEqual(self.source.execute('SELECT COUNT(*) FROM revisions').fetchone(), (0,))

    def test_reject_closed_loop(self):
        graph = TransitionGraph(('S',), 'S', (Transition('S', 'silent', 1, 'S'),))
        self.assert_rejected_without_revision(graph, 'cannot end')

    def test_reject_row_mass(self):
        graph = TransitionGraph(('S',), 'S', (Transition('S', 'end', Fraction(1000001, 1000000)),))
        self.assert_rejected_without_revision(graph, 'invalid probability row')

    def test_reject_zero_weight_end(self):
        graph = TransitionGraph(('S',), 'S', (Transition('S', 'silent', 1, 'S'), Transition('S', 'end', 0)))
        self.assert_rejected_without_revision(graph, 'cannot end')
        self.assertEqual(seal(self.source, serial_graph()), 1)

    def test_allow_unreachable_loop(self):
        graph = TransitionGraph(('S', 'unreachable'), 'S', (
            Transition('S', 'end', 1), Transition('S', 'silent', 0, 'unreachable'),
            Transition('unreachable', 'silent', 1, 'unreachable'),
        ))
        self.assertEqual(self.revisions.load(seal(self.source, graph)).graph, graph)

    def test_reject_unknown_public_code_and_reachable_trap(self):
        with self.assertRaisesRegex(ValueError, 'absent from the catalog'):
            seal(self.source, serial_graph('X'), catalog={})
        graph = TransitionGraph(('S', 'trap'), 'S', (
            Transition('S', 'end', Fraction(1, 2)), Transition('S', 'silent', Fraction(1, 2), 'trap'),
            Transition('trap', 'silent', 1, 'trap'),
        ))
        self.assert_rejected_without_revision(graph, 'cannot end')


class RunTests(LedgerTestCase):
    def test_prefix_is_not_complete(self):
        source = self.station('A')
        history = RunHistory(source)
        revision_id = seal(source, serial_graph('X', 'Y'))
        prefix = record_run(history, revision_id, ['X'])
        self.assertEqual(prefix.status, SupportStatus.OUTSIDE_PROTOCOL)
        self.assertEqual(prefix.codes, ('X',))
        self.assertEqual(prefix.revision_id, revision_id)
        self.assertEqual(history.for_revision(revision_id), (prefix,))
        self.assertEqual(record_run(history, revision_id, ['X', 'Y']).status, SupportStatus.SUPPORTED)

    def test_silent_tail_and_same_code(self):
        source = self.station('A')
        history = RunHistory(source)
        half = Fraction(1, 2)
        graph = TransitionGraph(('S', 'choose', 'alternate', 'tail', 'end'), 'S', (
            Transition('S', 'silent', 1, 'choose'),
            Transition('choose', 'public', half, 'alternate', 'X'),
            Transition('choose', 'public', half, 'tail', 'X'),
            Transition('alternate', 'public', 1, 'end', 'Y'),
            Transition('tail', 'silent', half, 'tail'), Transition('tail', 'silent', half, 'end'),
            Transition('end', 'end', 1),
        ))
        revision_id = seal(source, graph)
        for codes in (['X'], ['X', 'Y']):
            with self.subTest(codes=codes):
                self.assertEqual(record_run(history, revision_id, codes).status, SupportStatus.SUPPORTED)
        self.assertEqual(record_run(history, revision_id, []).status, SupportStatus.OUTSIDE_PROTOCOL)
        self.assertEqual(record_run(history, revision_id, ['未登记']).status, SupportStatus.OUTSIDE_PROTOCOL)

    def test_bad_input_leaves_no_run(self):
        source = self.station('A')
        history = RunHistory(source)
        revision_id = seal(source, serial_graph('X'))
        with self.assertRaises(KeyError):
            record_run(history, revision_id + 1, ['X'])
        for bad in ('X', [''], [1], None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                record_run(history, revision_id, bad)
        self.assertEqual(source.execute('SELECT COUNT(*) FROM observed_runs').fetchone(), (0,))
