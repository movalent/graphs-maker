"""Polynomial regression and confidence bands for scatter plots."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist


@dataclass(frozen=True, slots=True)
class CurveFit:
    """The fitted curve, confidence band, and equation for one series.

    Attributes:
        x: Evenly spaced x coordinates spanning the observed data.
        y: Predicted mean y values at ``x``.
        lower: Lower confidence limits at ``x``.
        upper: Upper confidence limits at ``x``.
        equation: Polynomial equation expressed in the original x coordinates.

    """

    x: tuple[float, ...]
    y: tuple[float, ...]
    lower: tuple[float, ...]
    upper: tuple[float, ...]
    equation: str


def _solve(matrix: list[list[float]], values: list[float]) -> list[float]:
    """Solve a small linear system with partial pivoting."""
    size = len(values)
    augmented = [[*row[:], value] for row, value in zip(matrix, values, strict=True)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError('the selected polynomial cannot be fitted to these x values')
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * pivot_value
                for value, pivot_value in zip(augmented[row], augmented[column], strict=True)
            ]
    return [augmented[row][-1] for row in range(size)]


def _inverse(matrix: list[list[float]]) -> list[list[float]]:
    """Invert a small matrix by solving once for each unit vector."""
    size = len(matrix)
    columns = [_solve(matrix, [float(row == column) for row in range(size)]) for column in range(size)]
    return [[columns[column][row] for column in range(size)] for row in range(size)]


def _beta_fraction(a: float, b: float, x: float) -> float:
    """Evaluate the continued fraction used by the regularized beta function."""
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    result = d
    for iteration in range(1, 201):
        m2 = 2 * iteration
        numerator = iteration * (b - iteration) * x / ((qam + m2) * (a + m2))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        result *= d * c
        numerator = -(a + iteration) * (qab + iteration) * x / ((a + m2) * (qap + m2))
        d = 1.0 + numerator * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + numerator / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        result *= delta
        if abs(delta - 1.0) < 3e-14:
            return result
    raise ArithmeticError('confidence interval calculation did not converge')


def _regularized_beta(x: float, a: float, b: float) -> float:
    """Return the regularized incomplete beta function."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_fraction(a, b, x) / a
    return 1.0 - front * _beta_fraction(b, a, 1.0 - x) / b


def _student_t_critical(confidence: float, degrees_freedom: int) -> float:
    """Return the two-sided Student t critical value for a confidence proportion."""
    if degrees_freedom >= 1000:
        return NormalDist().inv_cdf((1.0 + confidence) / 2.0)
    target = 1.0 - confidence
    low, high = 0.0, 1.0
    while _regularized_beta(degrees_freedom / (degrees_freedom + high * high), degrees_freedom / 2.0, 0.5) > target:
        high *= 2.0
    for _ in range(70):
        middle = (low + high) / 2.0
        tail = _regularized_beta(
            degrees_freedom / (degrees_freedom + middle * middle), degrees_freedom / 2.0, 0.5
        )
        if tail > target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _equation(coefficients: Sequence[float], center: float, scale: float) -> str:
    """Render normalized fit coefficients as an equation in the original x units."""
    degree = len(coefficients) - 1
    original = [0.0] * (degree + 1)
    for power, coefficient in enumerate(coefficients):
        for x_power in range(power + 1):
            original[x_power] += (
                coefficient
                * math.comb(power, x_power)
                * (-center) ** (power - x_power)
                / scale**power
            )
    terms: list[str] = []
    for power, coefficient in reversed(tuple(enumerate(original))):
        if abs(coefficient) < 1e-12:
            continue
        magnitude = f'{abs(coefficient):.4g}'
        variable = '' if power == 0 else 'x' if power == 1 else f'x^{power}'
        body = f'{magnitude}{variable}'
        if not terms:
            terms.append(f'-{body}' if coefficient < 0 else body)
        else:
            terms.append(f' - {body}' if coefficient < 0 else f' + {body}')
    return f'y = {"".join(terms) if terms else "0"}'


def fit_polynomial(
    x_values: Sequence[float],
    y_values: Sequence[float],
    degree: int,
    confidence: float = 0.95,
    points: int = 200,
) -> CurveFit:
    """Fit a polynomial and calculate a pointwise confidence band for its mean.

    Args:
        x_values: Observed x coordinates.
        y_values: Observed y coordinates, paired positionally with ``x_values``.
        degree: Polynomial degree, where one is linear regression.
        confidence: Confidence proportion between zero and one.
        points: Number of coordinates used to draw the fitted line and band.

    Returns:
        Fitted values, pointwise confidence limits, and a readable equation.

    Raises:
        ValueError: If the data cannot support the requested polynomial and its
            confidence band, or the confidence/point count is invalid.

    """
    if len(x_values) != len(y_values):
        raise ValueError('x and y values must have the same length')
    if degree < 1:
        raise ValueError('polynomial degree must be at least one')
    if not 0.0 < confidence < 1.0:
        raise ValueError('confidence must be between zero and one')
    if points < 2:
        raise ValueError('at least two points are needed to draw the curve')
    if not all(math.isfinite(value) for value in x_values) or not all(math.isfinite(value) for value in y_values):
        raise ValueError('fit data must contain only finite values')
    distinct = len(set(x_values))
    if distinct < degree + 1:
        raise ValueError(f'at least {degree + 1} distinct x values are required')
    if len(x_values) <= degree + 1:
        raise ValueError(f'at least {degree + 2} points are required to estimate a confidence band')

    center = (min(x_values) + max(x_values)) / 2.0
    scale = (max(x_values) - min(x_values)) / 2.0
    if scale == 0.0:
        raise ValueError('x values must not all be equal')
    normalized = [(value - center) / scale for value in x_values]
    columns = degree + 1
    design = [[value**power for power in range(columns)] for value in normalized]
    gram = [
        [math.fsum(row[left] * row[right] for row in design) for right in range(columns)]
        for left in range(columns)
    ]
    inverse = _inverse(gram)
    coefficients = _solve(
        gram,
        [math.fsum(row[power] * y for row, y in zip(design, y_values, strict=True)) for power in range(columns)],
    )
    residuals = [
        observed - math.fsum(coefficient * value**power for power, coefficient in enumerate(coefficients))
        for value, observed in zip(normalized, y_values, strict=True)
    ]
    variance = math.fsum(residual * residual for residual in residuals) / (len(x_values) - columns)
    critical = _student_t_critical(confidence, len(x_values) - columns)
    x_grid = tuple(min(x_values) + (max(x_values) - min(x_values)) * index / (points - 1) for index in range(points))
    predictions: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    for x_value in x_grid:
        basis = [((x_value - center) / scale) ** power for power in range(columns)]
        predicted = math.fsum(coefficient * value for coefficient, value in zip(coefficients, basis, strict=True))
        leverage = math.fsum(
            basis[left] * inverse[left][right] * basis[right]
            for left in range(columns)
            for right in range(columns)
        )
        margin = critical * math.sqrt(max(0.0, variance * leverage))
        predictions.append(predicted)
        lower.append(predicted - margin)
        upper.append(predicted + margin)
    return CurveFit(
        x=x_grid,
        y=tuple(predictions),
        lower=tuple(lower),
        upper=tuple(upper),
        equation=_equation(coefficients, center, scale),
    )
