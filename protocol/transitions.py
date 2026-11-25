from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from fractions import Fraction
from types import MappingProxyType

from protocol.catalog import require_text


State = str | int


class TransitionKind(str, Enum):
    SILENT = 'silent'
    PUBLIC = 'public'
    END = 'end'


def _check_state(state: State) -> None:
    if type(state) is not int:
        require_text(state, 'state')


@dataclass(frozen=True, slots=True)
class Transition:
    source: State
    kind: TransitionKind
    weight: Fraction
    target: State | None = None
    code: str | None = None

    def __post_init__(self):
        _check_state(self.source)
        kind = TransitionKind(self.kind)
        if type(self.weight) not in (int, Fraction):
            raise ValueError('transition weight must be an integer or Fraction')
        if kind is TransitionKind.END:
            if self.target is not None:
                raise ValueError('end transition cannot have a successor')
        else:
            _check_state(self.target)
        if kind is TransitionKind.PUBLIC:
            require_text(self.code, 'public code')
        elif self.code is not None:
            raise ValueError('only public transitions can carry a code')
        object.__setattr__(self, 'kind', kind)
        object.__setattr__(self, 'weight', Fraction(self.weight))


@dataclass(frozen=True, slots=True)
class TransitionGraph:
    states: tuple[State, ...]
    initial: State
    transitions: tuple[Transition, ...]
    _rows: Mapping[State, tuple[Transition, ...]] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        if not isinstance(self.states, (list, tuple)):
            raise ValueError('states must be a list or tuple')
        states = tuple(self.states)
        rows = {}
        for state in states:
            _check_state(state)
            if state in rows:
                raise ValueError(f'duplicate state {state!r}')
            rows[state] = []
        _check_state(self.initial)
        if self.initial not in rows:
            raise ValueError('initial state is undeclared')
        transitions = tuple(self.transitions)
        for edge in transitions:
            if not isinstance(edge, Transition):
                raise ValueError('graph edges must be Transition instances')
            if edge.source not in rows or (edge.target is not None and edge.target not in rows):
                raise ValueError('transition references an undeclared state')
            rows[edge.source].append(edge)
        object.__setattr__(self, 'states', states)
        object.__setattr__(self, 'transitions', transitions)
        object.__setattr__(self, '_rows', MappingProxyType({state: tuple(edges) for state, edges in rows.items()}))

    def outgoing(self, state: State) -> tuple[Transition, ...]:
        return self._rows[state]

    def positive_outgoing(self, state: State) -> Iterator[Transition]:
        return (edge for edge in self.outgoing(state) if edge.weight > 0)

    def reachable(self) -> frozenset[State]:
        found = {self.initial}
        pending = [self.initial]
        while pending:
            for edge in self.positive_outgoing(pending.pop()):
                if edge.target is not None and edge.target not in found:
                    found.add(edge.target)
                    pending.append(edge.target)
        return frozenset(found)


def transition_to_record(edge: Transition) -> list:
    weight = [edge.weight.numerator, edge.weight.denominator]
    return [edge.source, edge.kind.value, edge.target, edge.code, weight]


def transition_from_record(record: list) -> Transition:
    if not isinstance(record, list) or len(record) != 5:
        raise ValueError('expected a five-field transition record')
    source, kind, target, code, weight = record
    if (not isinstance(weight, list) or len(weight) != 2
            or any(type(part) is not int for part in weight) or weight[1] <= 0):
        raise ValueError('expected an integer rational pair with positive denominator')
    fraction = Fraction(*weight)
    if weight != [fraction.numerator, fraction.denominator]:
        raise ValueError('transition weight must be reduced')
    return Transition(source, kind, fraction, target, code)
