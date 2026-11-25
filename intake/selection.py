from dataclasses import dataclass

from intake.store import AcceptedPiece, IntakeStore


@dataclass(frozen=True, slots=True)
class AcceptedPair:
    left: AcceptedPiece
    right: AcceptedPiece


def select_pair(store: IntakeStore, left_id: int, right_id: int) -> AcceptedPair:
    pieces = []
    for position, intake_id in (('left', left_id), ('right', right_id)):
        try:
            pieces.append(store.read(intake_id))
        except (KeyError, ValueError) as exc:
            raise ValueError(f'{position} request does not name a valid accepted piece') from exc
    return AcceptedPair(*pieces)
