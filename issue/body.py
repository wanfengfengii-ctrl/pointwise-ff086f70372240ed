from dataclasses import dataclass
import json

from protocol.transitions import Transition, TransitionGraph, transition_from_record, transition_to_record
from protocol.validation import validate_probability_graph


@dataclass(frozen=True, slots=True)
class FixedBody:
    graph: TransitionGraph


def _edge_key(edge: Transition) -> tuple:
    return (edge.source, edge.kind.value, -1 if edge.target is None else edge.target,
            edge.code or '', edge.weight.numerator, edge.weight.denominator)


def _check_local_states(graph: TransitionGraph) -> None:
    if (any(type(state) is not int for state in graph.states)
            or type(graph.initial) is not int or graph.states != tuple(range(len(graph.states)))):
        raise ValueError('fixed piece must use contiguous local state numbers')


def encode_body(body: FixedBody) -> bytes:
    graph = body.graph
    _check_local_states(graph)
    document = {
        'state_count': len(graph.states), 'initial': graph.initial,
        'transitions': [transition_to_record(edge) for edge in sorted(graph.transitions, key=_edge_key)],
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def decode_body(raw: bytes) -> FixedBody:
    if type(raw) is not bytes:
        raise ValueError('fixed body must be bytes')
    document = json.loads(raw.decode('utf-8'))
    if not isinstance(document, dict) or document.keys() != {'state_count', 'initial', 'transitions'}:
        raise ValueError('invalid fixed body fields')
    count, initial, rows = document['state_count'], document['initial'], document['transitions']
    if type(count) is not int or type(initial) is not int or not isinstance(rows, list):
        raise ValueError('invalid fixed body structure')
    if not 0 <= initial < count <= len(rows):
        raise ValueError('invalid local state count or initial state')
    graph = TransitionGraph(tuple(range(count)), initial, tuple(transition_from_record(row) for row in rows))
    body = FixedBody(graph)
    _check_local_states(graph)
    validate_probability_graph(graph)
    if encode_body(body) != raw:
        raise ValueError('fixed body is not in canonical encoding')
    return body
