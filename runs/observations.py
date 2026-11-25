from dataclasses import dataclass
from enum import Enum

from protocol.catalog import require_text


class SupportStatus(str, Enum):
    SUPPORTED = 'supported'
    OUTSIDE_PROTOCOL = 'outside_protocol'


@dataclass(frozen=True, slots=True)
class ObservedRun:
    run_id: int
    revision_id: int
    codes: tuple[str, ...]
    status: SupportStatus


def validate_observation(codes) -> tuple[str, ...]:
    if not isinstance(codes, (tuple, list)):
        raise ValueError('observation must be a list or tuple of public codes')
    return tuple(require_text(code, 'observed public code') for code in codes)
