"""Precision and rate conversion shared by economics and projection."""

from decimal import Context, Decimal, ROUND_HALF_EVEN

from moneylab.domain.values import decimal_value


CALCULATION_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
ONE = Decimal(1)


def validate_annual_effective_rate(value: Decimal) -> None:
    decimal_value(value)
    if value <= -1:
        raise ValueError("annual effective rates must be greater than -1")


def monthly_effective_rate(annual: Decimal) -> Decimal:
    """Convert an effective annual rate using the caller's calculation context."""
    return (ONE + annual) ** (ONE / 12) - ONE
