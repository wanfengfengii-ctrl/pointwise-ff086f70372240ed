from protocol.transitions import TransitionGraph, TransitionKind
from runs.observations import SupportStatus


def _silent_closure(graph: TransitionGraph, states: set) -> set:
    reached = set(states)
    pending = list(states)
    while pending:
        for edge in graph.positive_outgoing(pending.pop()):
            if edge.kind is TransitionKind.SILENT and edge.target not in reached:
                reached.add(edge.target)
                pending.append(edge.target)
    return reached


def check_support(graph: TransitionGraph, codes: tuple[str, ...]) -> SupportStatus:
    states = _silent_closure(graph, {graph.initial})
    for code in codes:
        successors = {
            edge.target for state in states for edge in graph.positive_outgoing(state)
            if edge.kind is TransitionKind.PUBLIC and edge.code == code
        }
        if not successors:
            return SupportStatus.OUTSIDE_PROTOCOL
        states = _silent_closure(graph, successors)
    if any(edge.kind is TransitionKind.END for state in states for edge in graph.positive_outgoing(state)):
        return SupportStatus.SUPPORTED
    return SupportStatus.OUTSIDE_PROTOCOL
