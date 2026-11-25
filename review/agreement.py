from collections import defaultdict
from fractions import Fraction

from intake.selection import AcceptedPair
from issue.body import decode_body
from protocol.transitions import TransitionGraph, TransitionKind
from review.length import AgreementStatistics


def _completed_records(graph: TransitionGraph) -> dict[tuple[str, ...], Fraction]:
    records = defaultdict(Fraction)
    pending = [(graph.initial, (), Fraction(1), frozenset())]
    while pending:
        state, codes, mass, prior_states = pending.pop()
        visited = prior_states | {state}
        for edge in graph.positive_outgoing(state):
            contribution = mass * edge.weight
            if edge.kind is TransitionKind.END:
                records[codes] += contribution
            elif state not in prior_states:
                next_codes = codes + (edge.code,) if edge.kind is TransitionKind.PUBLIC else codes
                pending.append((edge.target, next_codes, contribution, visited))
    return dict(records)


def compute_agreement(pair: AcceptedPair) -> AgreementStatistics:
    left = _completed_records(decode_body(pair.left.envelope.body).graph)
    right = _completed_records(decode_body(pair.right.envelope.body).graph)
    probability = Fraction(0)
    length_mass = Fraction(0)
    for codes in left.keys() & right.keys():
        mass = left[codes] * right[codes]
        probability += mass
        length_mass += len(codes) * mass
    return AgreementStatistics.from_moments(probability, length_mass)
