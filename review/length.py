from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True, slots=True)
class AgreementStatistics:
    probability: Fraction
    mean_length: Fraction | None

    def __post_init__(self):
        if not isinstance(self.probability, Fraction) or not 0 <= self.probability <= 1:
            raise ValueError('agreement probability must be an exact value between zero and one')
        if self.probability == 0:
            if self.mean_length is not None:
                raise ValueError('zero agreement requires a null conditional length')
        elif not isinstance(self.mean_length, Fraction) or self.mean_length < 0:
            raise ValueError('conditional length must be an exact nonnegative value')

    @classmethod
    def from_moments(cls, probability: Fraction, length_mass: Fraction) -> 'AgreementStatistics':
        if length_mass < 0 or (not probability and length_mass):
            raise ValueError('invalid length mass for the agreement event')
        return cls(probability, length_mass / probability if probability else None)

    def to_record(self) -> dict:
        return {
            'probability': str(self.probability),
            'mean_length': None if self.mean_length is None else str(self.mean_length),
        }

    @classmethod
    def from_record(cls, record: dict) -> 'AgreementStatistics':
        length = record['mean_length']
        return cls(Fraction(record['probability']), None if length is None else Fraction(length))
