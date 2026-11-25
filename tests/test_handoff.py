from fractions import Fraction
import json

from intake.receive import PieceConflict, receive_piece
from issue.freeze import issue_revision
from issue.register import IssueRegister
from issue.retrieve import retrieve_piece
from tests.fixtures import LedgerTestCase, compliant_pair, fixture_record_mass, sample_graph, seal, serial_graph, wire_piece


class IntakeTests(LedgerTestCase):
    def assert_receipt_counts(self, center, accepted, conflicts):
        self.assertEqual(center.execute('SELECT COUNT(*) FROM accepted_pieces').fetchone(), (accepted,))
        self.assertEqual(center.execute('SELECT COUNT(*) FROM intake_receipts').fetchone(), (accepted,))
        self.assertEqual(center.execute('SELECT COUNT(*) FROM intake_conflicts').fetchone(), (conflicts,))

    def test_reissue_same_piece(self):
        source = self.station('A')
        center, intake, _ = self.center()
        register = IssueRegister(source, 'A')
        original = issue_revision(register, seal(source, serial_graph('X')))
        first = receive_piece(intake, original.raw)
        repeat = retrieve_piece(register, original.issue_id)
        self.assertEqual(repeat.raw, original.raw)
        self.assertEqual(receive_piece(intake, repeat.raw), first)
        self.assert_receipt_counts(center, 1, 0)

    def test_reissue_snapshot_and_reinitialize(self):
        source = self.station('A')
        center, intake, _ = self.center()
        old_revision = seal(source, serial_graph('X'))
        original = issue_revision(IssueRegister(source, 'A'), old_revision)
        first = receive_piece(intake, original.raw)
        new_revision = seal(source, serial_graph('Y'))
        self.assertNotEqual(old_revision, new_revision)
        source.close()
        center.close()
        reopened = self.station('A')
        new_center, new_intake, _ = self.center()
        repeat = retrieve_piece(IssueRegister(reopened, 'A'), original.issue_id)
        self.assertEqual(repeat.raw, original.raw)
        self.assertEqual(repeat.revision_id, old_revision)
        self.assertEqual(new_intake.read(first.intake_id), first)
        self.assertEqual(receive_piece(new_intake, repeat.raw), first)
        self.assert_receipt_counts(new_center, 1, 0)
        with self.assertRaises(KeyError):
            retrieve_piece(IssueRegister(reopened, 'A'), original.issue_id + 1)

    def test_conflicting_piece(self):
        center, intake, _ = self.center()
        initial, _ = compliant_pair()
        different = wire_piece('A', 7, 92, 1, [[0, 'end', None, None, [1, 1]]])
        first = receive_piece(intake, initial)
        with self.assertRaises(PieceConflict):
            receive_piece(intake, different)
        self.assertEqual(intake.read(first.intake_id), first)
        self.assertEqual(first.envelope.raw, initial)
        self.assertEqual(receive_piece(intake, initial).receipt, first.receipt)
        self.assert_receipt_counts(center, 1, 1)
        conflict = center.execute('SELECT first_intake_id, incoming_raw FROM intake_conflicts').fetchone()
        self.assertEqual(conflict, (first.intake_id, different))

    def test_silent_law_after_intake(self):
        source = self.station('A')
        _, intake, _ = self.center()
        first = self.ship(source, 'A', sample_graph('A'), intake)
        source.close()
        raw = intake.read(first.intake_id).envelope.raw
        self.assertEqual(fixture_record_mass(raw, ()), Fraction(3, 4))
        self.assertEqual(fixture_record_mass(raw, ('X',)), Fraction(1, 8))
        self.assertNotIn(b'bench-private', raw)
        self.assertNotIn(b'private-start', raw)
        self.assertNotIn(b'private-sampling', raw)
        self.assertEqual(set(json.loads(json.loads(raw)['body'])), {'initial', 'state_count', 'transitions'})

    def test_unknown_revision_does_not_issue(self):
        source = self.station('A')
        with self.assertRaises(KeyError):
            issue_revision(IssueRegister(source, 'A'), 1)
        self.assertEqual(source.execute('SELECT COUNT(*) FROM issued_pieces').fetchone(), (0,))

    def test_bad_piece_leaves_no_receipt(self):
        center, intake, _ = self.center()
        initial, _ = compliant_pair()
        damaged = json.loads(initial)
        damaged['body'] += ' '
        with self.assertRaisesRegex(ValueError, 'digest mismatch'):
            receive_piece(intake, json.dumps(damaged).encode('utf-8'))
        bad_graph = wire_piece('A', 7, 92, 1, [[0, 'silent', 0, None, [1, 1]], [0, 'end', None, None, [0, 1]]])
        with self.assertRaisesRegex(ValueError, 'cannot end'):
            receive_piece(intake, bad_graph)
        self.assert_receipt_counts(center, 0, 0)
        self.assertEqual(receive_piece(intake, initial).envelope.raw, initial)

    def test_same_number_different_site(self):
        center, intake, _ = self.center()
        left, right = compliant_pair()
        a, b = receive_piece(intake, left), receive_piece(intake, right)
        self.assertEqual(a.receipt.identity.issue_id, b.receipt.identity.issue_id)
        self.assertNotEqual(a.intake_id, b.intake_id)
        self.assertNotEqual(a.receipt.identity.site, b.receipt.identity.site)
        self.assert_receipt_counts(center, 2, 0)
