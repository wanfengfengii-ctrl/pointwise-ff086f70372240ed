import argparse
from contextlib import ExitStack, closing
from dataclasses import asdict
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from intake.receive import receive_piece
from intake.store import IntakeStore
from issue.freeze import issue_revision
from issue.register import IssueRegister
from issue.retrieve import retrieve_piece
from ledger import open_database
from protocol.catalog import build_catalog
from protocol.revisions import RevisionStore, seal_revision
from protocol.transitions import TransitionGraph, transition_from_record
from review.history import read_report
from review.publish import review_pair
from review.store import ReportStore
from runs.history import RunHistory
from runs.import_run import record_run


SAMPLES = Path(__file__).resolve().parent.parent / 'samples'


def _station(connection, site):
    revisions, runs, register = RevisionStore(connection), RunHistory(connection), IssueRegister(connection, site)
    for store in (revisions, runs, register):
        store.initialize()
    return revisions, runs, register


def _center(connection):
    intake, reports = IntakeStore(connection), ReportStore(connection)
    intake.initialize()
    reports.initialize()
    return intake, reports


def _seal_sample(revisions, sample):
    graph = TransitionGraph(tuple(sample['states']), sample['initial'],
                            tuple(transition_from_record(row) for row in sample['transitions']))
    return seal_revision(revisions, sample['protocol_id'], build_catalog(sample['catalog']), graph,
                         device_id=sample['device_id'])


def _business_check(case_id, expected, actual):
    if actual != expected:
        data = json.dumps({'case_id': case_id, 'expected': expected, 'actual': actual}, ensure_ascii=False)
        raise ValueError('POINTWISE_BUSINESS_FAILURE ' + data)


def run_day_sample(root: Path) -> dict:
    samples = [json.loads((SAMPLES / name).read_text(encoding='utf-8')) for name in ('station_a.json', 'station_b.json')]
    center_path = root / 'center.sqlite'
    station_paths = [root / 'station-a.sqlite', root / 'station-b.sqlite']
    trial_results = []
    received = []
    with closing(open_database(center_path)) as center:
        intake, reports = _center(center)
        with ExitStack() as stations:
            for path, sample in zip(station_paths, samples):
                source = stations.enter_context(closing(open_database(path)))
                revisions, history, register = _station(source, sample['site'])
                revision_id = _seal_sample(revisions, sample)
                runs = [record_run(history, revision_id, codes) for codes in sample['trial_runs']]
                trial_results.append([run.status.value for run in runs])
                piece = issue_revision(register, revision_id)
                first = receive_piece(intake, piece.raw)
                repeat = receive_piece(intake, retrieve_piece(register, piece.issue_id).raw)
                _business_check('v4', [first.intake_id, first.envelope.raw == piece.raw],
                                [repeat.intake_id, repeat == first])
                received.append(first)
        _business_check('v3', [['supported', 'supported', 'outside_protocol'], ['supported']], trial_results)
        signed = review_pair(reports, received[0].intake_id, received[1].intake_id)
        expected = {'probability': '1/4', 'mean_length': '1/3'}
        actual = signed.statistics.to_record()
        _business_check('v6', expected, actual)

    original = samples[0]
    correction = dict(original, **original['correction'])
    with closing(open_database(station_paths[0])) as source:
        revisions, history, register = _station(source, original['site'])
        new_revision = _seal_sample(revisions, correction)
        old = received[0].envelope
        _business_check('v4.reissue_snapshot', [True, True, 3], [
            new_revision != old.revision_id, retrieve_piece(register, old.issue_id).raw == old.raw,
            len(history.for_revision(old.revision_id)),
        ])

    with closing(open_database(center_path)) as center:
        intake, reports = _center(center)
        historical = read_report(reports, signed.report_id)
        parent_expectations = [asdict(piece.receipt) for piece in received]
        expected_parents = [
            {'intake_id': item['intake_id'], 'site': item['identity']['site'],
             'issue_id': item['identity']['issue_id'], 'revision_id': item['revision_id'],
             'body_sha256': item['body_sha256']}
            for item in parent_expectations
        ]
        downstream_expected = {'statistics': expected, 'parents': expected_parents,
                               'report_id': signed.report_id, 'receipt': signed.receipt}
        downstream_actual = {'statistics': historical.statistics.to_record(),
                             'parents': [asdict(parent) for parent in historical.parents],
                             'report_id': historical.report_id, 'receipt': historical.receipt}
        _business_check('v7', downstream_expected, downstream_actual)
        return {
            'case_id': 'v6', 'input': {'sites': [sample['site'] for sample in samples],
                                      'transitions': [sample['transitions'] for sample in samples],
                                      'intake_ids': [piece.intake_id for piece in received]},
            'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': ['issue/freeze.py', 'intake/receive.py', 'intake/selection.py',
                           'review/agreement.py', 'review/store.py', 'review/history.py'],
            'oracle': '共同空记录质量为 3/16。非空质量从 3/64 起按 1/4 递减，和为 1/16，长度质量为 1/12。父件出处取实际首次实收回执。',
        }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='海岚检测实验室规程复盘台账')
    parser.add_argument('command', choices=('demo',))
    parser.parse_args(argv)
    try:
        with TemporaryDirectory(prefix='hailan-review-') as directory:
            evidence = run_day_sample(Path(directory))
    except (ValueError, KeyError, sqlite3.Error, OSError) as error:
        parser.exit(1, f'{error}\n')
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
