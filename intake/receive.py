from intake.store import AcceptedPiece, IntakeStore
from issue.body import decode_body
from issue.envelope import decode_envelope


class PieceConflict(ValueError):
    pass


def receive_piece(store: IntakeStore, raw: bytes) -> AcceptedPiece:
    envelope = decode_envelope(raw)
    decode_body(envelope.body)
    accepted = store.accept_or_register_conflict(envelope)
    if accepted is None:
        raise PieceConflict(f'conflicting issue {envelope.site!r}/{envelope.issue_id}')
    return accepted
