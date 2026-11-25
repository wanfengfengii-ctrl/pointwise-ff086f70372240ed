from dataclasses import dataclass
import json

from intake.identity import PieceIdentity, identify_piece
from issue.envelope import IssuedEnvelope


@dataclass(frozen=True, slots=True)
class IntakeReceipt:
    intake_id: int
    identity: PieceIdentity
    revision_id: int
    body_sha256: str


def make_intake_receipt(intake_id: int, envelope: IssuedEnvelope) -> IntakeReceipt:
    return IntakeReceipt(intake_id, identify_piece(envelope), envelope.revision_id, envelope.body_sha256)


def encode_intake_receipt(receipt: IntakeReceipt) -> str:
    return json.dumps({
        'intake_id': receipt.intake_id, 'site': receipt.identity.site, 'issue_id': receipt.identity.issue_id,
        'revision_id': receipt.revision_id, 'body_sha256': receipt.body_sha256,
    }, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def decode_intake_receipt(text: str) -> IntakeReceipt:
    record = json.loads(text)
    return IntakeReceipt(record['intake_id'], PieceIdentity(record['site'], record['issue_id']),
                         record['revision_id'], record['body_sha256'])
