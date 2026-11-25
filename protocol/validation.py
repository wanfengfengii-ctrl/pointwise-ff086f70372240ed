from protocol.catalog import CodeCatalog
from protocol.transitions import TransitionGraph, TransitionKind


def validate_probability_graph(graph: TransitionGraph) -> None:
    if not isinstance(graph, TransitionGraph):
        raise ValueError('expected a TransitionGraph')
    predecessors = {state: set() for state in graph.states}
    can_end = set()
    for state in graph.states:
        row = graph.outgoing(state)
        if any(edge.weight < 0 for edge in row) or sum(edge.weight for edge in row) != 1:
            raise ValueError(f'invalid probability row for state {state!r}')
        for edge in graph.positive_outgoing(state):
            if edge.kind is TransitionKind.END:
                can_end.add(state)
            else:
                predecessors[edge.target].add(state)
    pending = list(can_end)
    while pending:
        for parent in predecessors[pending.pop()] - can_end:
            can_end.add(parent)
            pending.append(parent)
    if graph.reachable() - can_end:
        raise ValueError('a positive-probability reachable state cannot end')


def validate_revision(catalog: CodeCatalog, graph: TransitionGraph) -> None:
    if not isinstance(catalog, CodeCatalog):
        raise ValueError('expected a CodeCatalog')
    validate_probability_graph(graph)
    if any(not isinstance(state, str) for state in graph.states):
        raise ValueError('station state names must be text')
    codes = catalog.codes
    for edge in graph.transitions:
        if edge.kind is TransitionKind.PUBLIC and edge.code not in codes:
            raise ValueError(f'public code {edge.code!r} is absent from the catalog')
