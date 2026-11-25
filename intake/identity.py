from dataclasses import dataclass

from issue.envelope import IssuedEnvelope


@dataclass(frozen=True, slots=True)
class PieceIdentity:
    site: str
    issue_id: int


def identify_piece(envelope: IssuedEnvelope) -> PieceIdentity:
    return PieceIdentity(envelope.site, envelope.issue_id)


def same_piece(first: IssuedEnvelope, incoming: IssuedEnvelope) -> bool:
    return (identify_piece(first) == identify_piece(incoming)
            and first.revision_id == incoming.revision_id and first.raw == incoming.raw)
