from collections import defaultdict
from fractions import Fraction

from intake.selection import AcceptedPair
from issue.body import decode_body
from protocol.transitions import TransitionGraph, TransitionKind
from review.length import AgreementStatistics
from review.linear_system import RationalSystem


def _reachable_states(graph: TransitionGraph) -> tuple:
    """Positive-probability reachable states in declaration order."""
    reachable = graph.reachable()
    return tuple(state for state in graph.states if state in reachable)


def _silent_closure(graph: TransitionGraph, states: tuple) -> dict:
    """Exact probability of reaching each state through zero or more silent edges.

    The silent edges form a substochastic matrix Q; because every reachable state
    can end with positive probability, Q is transient and (I - Q) is invertible.
    """
    index = {state: position for position, state in enumerate(states)}
    size = len(states)
    identity = tuple(tuple(int(row == column) for column in range(size)) for row in range(size))
    coefficients = [[Fraction(value) for value in row] for row in identity]
    for state in states:
        source = index[state]
        for edge in graph.positive_outgoing(state):
            if edge.kind is TransitionKind.SILENT:
                coefficients[source][index[edge.target]] -= edge.weight
    system = RationalSystem(coefficients)
    columns = [system.solve(identity[row]) for row in range(size)]
    return {(source, target): columns[index[target]][index[source]]
            for source in states for target in states}


def _embedded_chain(graph: TransitionGraph, states: tuple) -> tuple:
    """Jump chain on the observable events: one public code, or termination.

    Returns (termination_probability, public_moves) where public_moves maps a
    public code to {(source, target): probability}. Silent edges are collapsed
    away, including arbitrarily many silent loops and same-code branches.
    """
    closure = _silent_closure(graph, states)
    termination = {}
    moves = defaultdict(lambda: defaultdict(Fraction))
    for source in states:
        end_mass = Fraction(0)
        for middle in states:
            prefix = closure[(source, middle)]
            if not prefix:
                continue
            for edge in graph.positive_outgoing(middle):
                if edge.kind is TransitionKind.END:
                    end_mass += prefix * edge.weight
                elif edge.kind is TransitionKind.PUBLIC:
                    moves[edge.code][(source, edge.target)] += prefix * edge.weight
        termination[source] = end_mass
    return termination, {code: dict(weights) for code, weights in moves.items()}


def compute_agreement(pair: AcceptedPair) -> AgreementStatistics:
    left_graph = decode_body(pair.left.envelope.body).graph
    right_graph = decode_body(pair.right.envelope.body).graph
    left_states = _reachable_states(left_graph)
    right_states = _reachable_states(right_graph)
    left_end, left_moves = _embedded_chain(left_graph, left_states)
    right_end, right_moves = _embedded_chain(right_graph, right_states)

    positions = {(left, right): offset
                 for offset, (left, right) in enumerate(
                     (left_state, right_state)
                     for left_state in left_states for right_state in right_states)}
    size = len(positions)
    transitions = [[Fraction(0) for _ in range(size)] for _ in range(size)]
    empty_ends = [Fraction(0) for _ in range(size)]
    for (left_state, right_state), row in positions.items():
        empty_ends[row] = left_end[left_state] * right_end[right_state]
        for code in left_moves.keys() & right_moves.keys():
            left_weights = left_moves[code]
            right_weights = right_moves[code]
            for (left_from, left_to), left_weight in left_weights.items():
                if left_from != left_state:
                    continue
                for (right_from, right_to), right_weight in right_weights.items():
                    if right_from != right_state:
                        continue
                    transitions[row][positions[(left_to, right_to)]] += left_weight * right_weight

    system = RationalSystem([[Fraction(int(row == column)) - transitions[row][column]
                              for column in range(size)] for row in range(size)])
    completion = system.solve(empty_ends)
    extended = [sum(transitions[row][column] * completion[column] for column in range(size))
                for row in range(size)]
    length_mass_per_state = system.solve(extended)

    start = positions[(left_graph.initial, right_graph.initial)]
    return AgreementStatistics.from_moments(completion[start], length_mass_per_state[start])
