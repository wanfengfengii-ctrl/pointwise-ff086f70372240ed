"""Regression coverage for the fixed issuance and agreement defects."""
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from intake.receive import receive_piece
from issue.body import decode_body
from issue.freeze import issue_revision
from issue.register import IssueRegister
from protocol.transitions import Transition, TransitionGraph, TransitionKind
from review.cli import run_day_sample
from review.publish import review_pair
from tests.fixtures import LedgerTestCase, fixture_record_mass, sample_graph, seal, serial_graph, wire_piece


class IssueProjectionRegressionTests(LedgerTestCase):
    def test_silent_edges_survive_projection(self):
        source = self.station('A')
        _, intake, _ = self.center()
        revision_id = seal(source, sample_graph('A'))
        piece = issue_revision(IssueRegister(source, 'A'), revision_id)
        body = decode_body(piece.body).graph
        silent = [edge for edge in body.transitions if edge.kind is TransitionKind.SILENT]
        self.assertEqual(len(silent), 1)
        self.assertIsNotNone(silent[0].target)
        accepted = receive_piece(intake, piece.raw)
        document = decode_body(accepted.envelope.body).graph
        self.assertIn('silent', {edge.kind.value for edge in document.transitions})

    def test_projection_preserves_record_mass(self):
        _, intake, _ = self.center()
        expectations = {
            'A': {(): Fraction(3, 4), ('X',): Fraction(1, 8)},
            'B': {(): Fraction(1, 4), ('X',): Fraction(3, 8)},
        }
        for site, masses in expectations.items():
            source = self.station(site)
            accepted = self.ship(source, site, sample_graph(site), intake)
            source.close()
            for codes, expected in masses.items():
                with self.subTest(site=site, codes=codes):
                    self.assertEqual(fixture_record_mass(accepted.envelope.raw, codes), expected)
            self.assertNotIn(b'private-', accepted.envelope.raw)
            self.assertNotIn('设备'.encode('utf-8'), accepted.envelope.body)

    def test_cyclic_projection_and_self_agreement(self):
        # Silent and public self-loops must both be projected intact.  For the
        # one-state graph the empty record has mass 1/2 and length-n records
        # 2**-(n+1); two independent runs agree with probability 1/3 at mean
        # length 1/3.
        source = self.station('A')
        _, intake, reports = self.center()
        half = Fraction(1, 2)
        graph = TransitionGraph(('bench',), 'bench', (
            Transition('bench', 'silent', half, 'bench'),
            Transition('bench', 'public', Fraction(1, 4), 'bench', 'X'),
            Transition('bench', 'end', Fraction(1, 4)),
        ))
        accepted = self.ship(source, 'A', graph, intake)
        source.close()
        signed = review_pair(reports, accepted.intake_id, accepted.intake_id)
        self.assertEqual((signed.statistics.probability, signed.statistics.mean_length),
                         (Fraction(1, 3), Fraction(1, 3)))


class AgreementRegressionTests(LedgerTestCase):
    def test_empty_and_repeated_codes_with_cycles(self):
        _, intake, reports = self.center()
        a = receive_piece(intake, wire_piece('A', 1, 1, 1, [
            [0, 'silent', 0, None, [1, 2]], [0, 'public', 0, 'X', [1, 4]],
            [0, 'end', None, None, [1, 4]],
        ]))
        b = receive_piece(intake, wire_piece('B', 1, 1, 1, [
            [0, 'silent', 0, None, [1, 2]], [0, 'public', 0, 'X', [1, 4]],
            [0, 'end', None, None, [1, 4]],
        ]))
        signed = review_pair(reports, a.intake_id, b.intake_id)
        self.assertEqual((signed.statistics.probability, signed.statistics.mean_length),
                         (Fraction(1, 3), Fraction(1, 3)))

    def test_same_piece_both_positions_is_independent(self):
        _, intake, reports = self.center()
        a, _ = self.ship_sample_pair(intake)
        signed = review_pair(reports, a.intake_id, a.intake_id)
        # 甲站记录质量：空 3/4，长度 n 为 2**-(n+2)；独立两次运行下
        # 概率 9/16 + sum (2**-(n+2))**2 = 7/12，长度质量 1/36。
        self.assertEqual((signed.statistics.probability, signed.statistics.mean_length),
                         (Fraction(7, 12), Fraction(1, 21)))

    def test_disjoint_codes_yield_null_length(self):
        _, intake, reports = self.center()
        x = receive_piece(intake, wire_piece('A', 1, 1, 2, [
            [0, 'public', 1, 'X', [1, 1]], [1, 'end', None, None, [1, 1]]]))
        y = receive_piece(intake, wire_piece('B', 1, 1, 2, [
            [0, 'public', 1, 'Y', [1, 1]], [1, 'end', None, None, [1, 1]]]))
        signed = review_pair(reports, x.intake_id, y.intake_id)
        self.assertIsNone(signed.statistics.mean_length)
        self.assertEqual(signed.statistics.probability, 0)


class DemoRegressionTests(unittest.TestCase):
    def test_day_sample_reports_expected_values(self):
        with TemporaryDirectory(prefix='hailan-regression-') as directory:
            evidence = run_day_sample(Path(directory))
        self.assertEqual(evidence['case_id'], 'v6')
        self.assertEqual(evidence['actual'], {'probability': '1/4', 'mean_length': '1/3'})
        self.assertEqual(evidence['actual'], evidence['expected'])
        self.assertEqual(evidence['downstream_actual'], evidence['downstream_expected'])
