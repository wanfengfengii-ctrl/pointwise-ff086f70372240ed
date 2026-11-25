from protocol.revisions import RevisionStore
from runs.history import RunHistory
from runs.observations import ObservedRun, validate_observation
from runs.support_check import check_support


def record_run(history: RunHistory, revision_id: int, codes) -> ObservedRun:
    sequence = validate_observation(codes)
    revision = RevisionStore(history.connection).load(revision_id)
    status = check_support(revision.graph, sequence)
    return history.append(revision.revision_id, sequence, status)
