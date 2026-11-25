from fractions import Fraction
import sqlite3

from intake.receive import receive_piece
from protocol.transitions import Transition, TransitionGraph
from review.history import read_report
from review.linear_system import solve_rational_system
from review.publish import review_pair
from tests.fixtures import LedgerTestCase, compliant_pair, seal, serial_graph, wire_piece


class ReviewTests(LedgerTestCase):
    def assert_statistics(self, report, probability, mean_length):
        actual = (report.statistics.probability, report.statistics.mean_length)
        self.assertIsInstance(actual[0], Fraction)
        if mean_length is not None:
            self.assertIsInstance(actual[1], Fraction)
        self.assertEqual(actual, (probability, mean_length))

    def assert_sample_statistics(self, report):
        self.assert_statistics(report, Fraction(1, 4), Fraction(1, 3))

    def counts(self, connection):
        return tuple(connection.execute(query).fetchone()[0] for query in (
            'SELECT COUNT(*) FROM reports', 'SELECT COUNT(*) FROM report_parents',
            'SELECT COUNT(*) FROM report_receipts',
        ))

    def test_silent_reset_joint_report(self):
        _, intake, reports = self.center()
        a, b = self.ship_sample_pair(intake)
        signed = review_pair(reports, a.intake_id, b.intake_id)
        self.assert_sample_statistics(signed)
        self.assertEqual(tuple(parent.intake_id for parent in signed.parents), (a.intake_id, b.intake_id))
        self.assertEqual(read_report(reports, signed.report_id), signed)

    def test_compliant_pair_without_source(self):
        _, intake, reports = self.center()
        a, b = [receive_piece(intake, raw) for raw in compliant_pair()]
        signed = review_pair(reports, a.intake_id, b.intake_id)
        self.assert_sample_statistics(signed)
        self.assertEqual([parent.revision_id for parent in signed.parents], [92, 56])

    def test_requested_pair_ignores_later_intake(self):
        _, intake, reports = self.center()
        a, b = self.ship_sample_pair(intake)
        correction = self.station('B')
        newer = self.ship(correction, 'B', serial_graph(), intake)
        correction.close()
        self.assertNotEqual(newer.intake_id, b.intake_id)
        signed = review_pair(reports, a.intake_id, b.intake_id)
        self.assert_sample_statistics(signed)
        self.assertEqual(signed.parents[1].intake_id, b.intake_id)
        self.assertEqual(signed.parents[1].body_sha256, b.envelope.body_sha256)
        self.assert_statistics(review_pair(reports, a.intake_id, newer.intake_id), Fraction(3, 4), Fraction(0))

    def test_same_code_different_successors(self):
        _, intake, reports = self.center()
        source = self.station('A')
        graph = TransitionGraph(('S', 'one', 'two'), 'S', (
            Transition('S', 'public', Fraction(1, 2), 'one', 'X'),
            Transition('S', 'public', Fraction(1, 2), 'two', 'X'),
            Transition('one', 'end', 1), Transition('two', 'end', 1),
        ))
        a = self.ship(source, 'A', graph, intake)
        b = self.ship(source, 'A', serial_graph('X'), intake)
        source.close()
        self.assert_statistics(review_pair(reports, a.intake_id, b.intake_id), Fraction(1), Fraction(1))

    def test_silent_loops_do_not_count_as_codes(self):
        _, intake, reports = self.center()
        a = receive_piece(intake, wire_piece('A', 1, 1, 3, [
            [0, 'silent', 0, None, [1, 2]], [0, 'silent', 1, None, [1, 4]],
            [0, 'public', 2, 'X', [1, 4]], [1, 'silent', 1, None, [3, 4]],
            [1, 'end', None, None, [1, 4]], [2, 'end', None, None, [1, 1]],
        ]))
        b = receive_piece(intake, wire_piece('B', 1, 1, 1, [[0, 'end', None, None, [1, 1]]]))
        self.assert_statistics(review_pair(reports, a.intake_id, b.intake_id), Fraction(1, 2), Fraction(0))

    def test_zero_overlap_and_empty_match(self):
        _, intake, reports = self.center()
        source = self.station('A')
        x = self.ship(source, 'A', serial_graph('X'), intake)
        y = self.ship(source, 'A', serial_graph('Y'), intake)
        empty_a = self.ship(source, 'A', serial_graph(), intake)
        empty_b = receive_piece(intake, wire_piece('B', 1, 1, 1, [[0, 'end', None, None, [1, 1]]]))
        source.close()
        no_match = review_pair(reports, x.intake_id, y.intake_id)
        empty_match = review_pair(reports, empty_a.intake_id, empty_b.intake_id)
        self.assert_statistics(no_match, Fraction(0), None)
        self.assert_statistics(empty_match, Fraction(1), Fraction(0))
        self.assertEqual(read_report(reports, no_match.report_id), no_match)
        self.assertEqual(read_report(reports, empty_match.report_id), empty_match)

    def test_read_after_revision(self):
        center, intake, reports = self.center()
        a, b = self.ship_sample_pair(intake)
        signed = review_pair(reports, a.intake_id, b.intake_id)
        source = self.station('A')
        revision = seal(source, serial_graph('Y'))
        self.assertNotEqual(revision, a.envelope.revision_id)
        source.close()
        center.close()
        _, _, reopened_reports = self.center()
        historical = read_report(reopened_reports, signed.report_id)
        self.assert_sample_statistics(historical)
        self.assertEqual(historical, signed)
        self.assertEqual([parent.revision_id for parent in historical.parents],
                         [a.envelope.revision_id, b.envelope.revision_id])

    def test_parent_order_survives_reopen(self):
        center, intake, reports = self.center()
        a, b = self.ship_sample_pair(intake)
        signed = review_pair(reports, b.intake_id, a.intake_id)
        center.close()
        _, _, reopened = self.center()
        historical = read_report(reopened, signed.report_id)
        self.assert_sample_statistics(historical)
        self.assertEqual([parent.intake_id for parent in historical.parents], [b.intake_id, a.intake_id])
        self.assertEqual([parent.site for parent in historical.parents], ['B', 'A'])
        self.assertEqual(historical, signed)

    def test_unknown_report(self):
        center, _, reports = self.center()
        with self.assertRaises(KeyError):
            read_report(reports, 1)
        self.assertEqual(self.counts(center), (0, 0, 0))

    def test_invalid_parent(self):
        center, intake, reports = self.center()
        a, _ = self.ship_sample_pair(intake)
        for ids in ((99, a.intake_id), (a.intake_id, 99), (a.intake_id, True)):
            with self.subTest(ids=ids), self.assertRaisesRegex(ValueError, 'valid accepted piece'):
                review_pair(reports, *ids)
        self.assertEqual(self.counts(center), (0, 0, 0))
        self.assertEqual(intake.read(a.intake_id), a)

    def test_publish_rollback(self):
        center, intake, reports = self.center()
        a, b = self.ship_sample_pair(intake)
        center.execute('''CREATE TABLE commit_fault (
            report_id INTEGER PRIMARY KEY,
            invalid_intake INTEGER NOT NULL REFERENCES accepted_pieces(intake_id)
                DEFERRABLE INITIALLY DEFERRED
        )''')
        center.execute('''CREATE TRIGGER fail_at_report_commit AFTER INSERT ON report_receipts BEGIN
            INSERT INTO commit_fault VALUES (NEW.report_id, -1);
        END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'FOREIGN KEY constraint failed'):
            review_pair(reports, a.intake_id, b.intake_id)
        self.assertFalse(center.in_transaction)
        self.assertEqual(self.counts(center), (0, 0, 0))
        self.assertEqual(center.execute('SELECT COUNT(*) FROM commit_fault').fetchone(), (0,))
        with self.assertRaises(KeyError):
            read_report(reports, 1)
        self.assertEqual((intake.read(a.intake_id), intake.read(b.intake_id)), (a, b))
        center.execute('DROP TRIGGER fail_at_report_commit')
        retried = review_pair(reports, a.intake_id, b.intake_id)
        self.assert_sample_statistics(retried)
        self.assertEqual(self.counts(center), (1, 2, 1))
        self.assertEqual(read_report(reports, retried.report_id), retried)

    def test_exact_elimination_with_pivot_and_singularity(self):
        self.assertEqual(solve_rational_system(((0, 3), (2, 1)), (1, 2)),
                         (Fraction(5, 6), Fraction(1, 3)))
        with self.assertRaisesRegex(ValueError, 'unique solution'):
            solve_rational_system(((1, 2), (2, 4)), (3, 6))
