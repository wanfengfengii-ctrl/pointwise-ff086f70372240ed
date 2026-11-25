from collections.abc import Sequence
from fractions import Fraction


Rational = int | Fraction


class RationalSystem:
    """Factor an exact square matrix once and solve for successive right-hand sides."""

    def __init__(self, coefficients: Sequence[Sequence[Rational]]):
        size = len(coefficients)
        if any(len(row) != size for row in coefficients):
            raise ValueError('coefficient matrix must be square')
        self.factors = [[Fraction(value) for value in row] for row in coefficients]
        self.permutation = list(range(size))
        for column in range(size):
            pivot = next((row for row in range(column, size) if self.factors[row][column]), None)
            if pivot is None:
                raise ValueError('linear system does not have a unique solution')
            self.factors[column], self.factors[pivot] = self.factors[pivot], self.factors[column]
            self.permutation[column], self.permutation[pivot] = self.permutation[pivot], self.permutation[column]
            pivot_row = self.factors[column]
            for row in self.factors[column + 1:]:
                if row[column]:
                    multiplier = row[column] / pivot_row[column]
                    row[column] = multiplier
                    for k in range(column + 1, size):
                        row[k] -= multiplier * pivot_row[k]

    def solve(self, right_hand_side: Sequence[Rational]) -> tuple[Fraction, ...]:
        size = len(self.permutation)
        if len(right_hand_side) != size:
            raise ValueError('right-hand side has the wrong length')
        values = [Fraction(right_hand_side[index]) for index in self.permutation]
        for i, row in enumerate(self.factors):
            values[i] -= sum(row[j] * values[j] for j in range(i))
        for i in range(size - 1, -1, -1):
            row = self.factors[i]
            values[i] = (values[i] - sum(row[j] * values[j] for j in range(i + 1, size))) / row[i]
        return tuple(values)


def solve_rational_system(coefficients: Sequence[Sequence[Rational]],
                          right_hand_side: Sequence[Rational]) -> tuple[Fraction, ...]:
    return RationalSystem(coefficients).solve(right_hand_side)
