from issue.body import FixedBody, encode_body
from issue.envelope import IssuedEnvelope
from issue.register import IssueRegister
from protocol.revisions import FrozenRevision, RevisionStore
from protocol.transitions import Transition, TransitionGraph, TransitionKind


def project_revision(revision: FrozenRevision) -> FixedBody:
    graph = revision.graph
    local = {state: index for index, state in enumerate(graph.states)}
    transitions = []
    for edge in graph.transitions:
        if edge.kind is TransitionKind.END:
            transitions.append(Transition(local[edge.source], TransitionKind.END, edge.weight))
            continue
        successor = local[edge.target]
        transitions.append(Transition(local[edge.source], edge.kind, edge.weight, successor, edge.code))
    return FixedBody(TransitionGraph(tuple(range(len(local))), local[graph.initial], tuple(transitions)))


def issue_revision(register: IssueRegister, revision_id: int) -> IssuedEnvelope:
    revision = RevisionStore(register.connection).load(revision_id)
    return register.create(revision.revision_id, encode_body(project_revision(revision)))
