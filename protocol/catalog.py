from collections.abc import Mapping
from dataclasses import dataclass


def require_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f'{field} must be nonempty text')
    value.encode('utf-8')
    return value


@dataclass(frozen=True, slots=True)
class CodeCatalog:
    entries: tuple[tuple[str, str], ...]

    def __post_init__(self):
        entries = tuple(tuple(entry) for entry in self.entries)
        known = set()
        for code, description in entries:
            require_text(code, 'public code')
            require_text(description, 'code description')
            if code in known:
                raise ValueError(f'duplicate public code {code!r}')
            known.add(code)
        object.__setattr__(self, 'entries', entries)

    @property
    def codes(self) -> frozenset[str]:
        return frozenset(code for code, _ in self.entries)


def build_catalog(entries: Mapping[str, str]) -> CodeCatalog:
    if not isinstance(entries, Mapping):
        raise ValueError('catalog must map codes to descriptions')
    return CodeCatalog(tuple(entries.items()))
