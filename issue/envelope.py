from dataclasses import dataclass
from hashlib import sha256
import json

from ledger import record_id
from protocol.catalog import require_text


@dataclass(frozen=True, slots=True)
class IssuedEnvelope:
    site: str
    issue_id: int
    revision_id: int
    body_sha256: str
    body: bytes
    raw: bytes


def _unique_fields(pairs):
    fields = {}
    for key, value in pairs:
        if key in fields:
            raise ValueError(f'duplicate envelope field {key!r}')
        fields[key] = value
    return fields


def encode_envelope(site: str, issue_id: int, revision_id: int, body: bytes) -> bytes:
    if type(body) is not bytes:
        raise ValueError('fixed body must be bytes')
    document = {
        'version': 1, 'site': require_text(site, 'issuing site'), 'issue_id': record_id(issue_id),
        'revision_id': record_id(revision_id), 'body_sha256': sha256(body).hexdigest(),
        'body': body.decode('utf-8'),
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def decode_envelope(raw: bytes) -> IssuedEnvelope:
    if type(raw) is not bytes:
        raise ValueError('piece must be received as bytes')
    document = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_fields)
    fields = {'version', 'site', 'issue_id', 'revision_id', 'body_sha256', 'body'}
    if not isinstance(document, dict) or document.keys() != fields:
        raise ValueError('invalid fixed piece envelope fields')
    if type(document['version']) is not int or document['version'] != 1:
        raise ValueError('unsupported fixed piece version')
    site = require_text(document['site'], 'issuing site')
    issue_id = record_id(document['issue_id'])
    revision_id = record_id(document['revision_id'])
    body = require_text(document['body'], 'fixed body').encode('utf-8')
    digest = sha256(body).hexdigest()
    if document['body_sha256'] != digest:
        raise ValueError('fixed body digest mismatch')
    return IssuedEnvelope(site, issue_id, revision_id, digest, body, raw)
