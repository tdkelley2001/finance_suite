"""Deterministic rate conversion, postings and reconciliation."""

from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext

from .results import (
    EffectKind, FinancialEffect, Observation, PositionBalance, PositionKind, Reconciliation,
)


ZERO = Decimal(0)
ONE = Decimal(1)
MONEY_QUANTUM = Decimal("0.00000001")
CALCULATION_CONTEXT = Context(prec=60, rounding=ROUND_HALF_EVEN)
AMOUNT_LIMIT = Decimal("1e30")


class ProjectionRangeError(ArithmeticError):
    """A calculated amount exceeds the supported numerical range."""


class ReconciliationError(ArithmeticError):
    """Projected closing positions disagree with recorded financial effects."""


def money_round(amount: Decimal) -> Decimal:
    if not amount.is_finite() or abs(amount) >= AMOUNT_LIMIT:
        raise ProjectionRangeError("projection amounts require fewer than 31 integer places")
    rounded = amount.quantize(MONEY_QUANTUM)
    if abs(rounded) >= AMOUNT_LIMIT:
        raise ProjectionRangeError("rounded amount reached the projection amount limit")
    return rounded


def monthly_effective_rate(annual: Decimal) -> Decimal:
    return (ONE + annual) ** (ONE / 12) - ONE


def add_postings(opening: dict[str, Decimal], effects: tuple[FinancialEffect, ...]) -> dict[str, Decimal]:
    closing = dict(opening)
    for effect in effects:
        for posting in effect.postings:
            closing[posting.position_id] += posting.change
    return closing


def net_worth(balances: dict[str, Decimal], kinds: dict[str, PositionKind]) -> Decimal:
    return sum(((-amount if kinds[key] is PositionKind.LIABILITY else amount)
                for key, amount in balances.items()), start=ZERO)


def reconcile(opening, closing, kinds, effects) -> Reconciliation:
    """Check every position and independently price economic effects by category."""
    with localcontext(CALCULATION_CONTEXT):
        if any(balance < 0 for balance in closing.values()):
            raise ReconciliationError("closing position cannot be negative")
        posted = add_postings(opening, effects)
        if closing.keys() != posted.keys() or kinds.keys() != opening.keys():
            raise ReconciliationError("opening and closing position catalogs differ")
        residuals = {key: closing[key] - posted[key] for key in posted}
        mismatched = [key for key, value in residuals.items() if value]
        if mismatched:
            raise ReconciliationError(f"position postings do not reconcile for {', '.join(mismatched)}")
        positive = {EffectKind.INCOME, EffectKind.ACCOUNT_RETURN, EffectKind.ASSET_REVALUATION}
        negative = {EffectKind.EXPENSE, EffectKind.INTEREST_ACCRUED}
        economics = ZERO
        for effect in effects:
            if effect.kind in positive:
                economics += effect.amount
            elif effect.kind in negative:
                economics -= effect.amount
        residual = net_worth(closing, kinds) - net_worth(opening, kinds) - economics
        if residual:
            raise ReconciliationError(f"net worth does not reconcile: residual {residual}")
        return Reconciliation(max(map(abs, residuals.values()), default=ZERO), residual, economics)


def observe(as_of, balances, kinds, inflation_index, real_dollars) -> Observation:
    positions = tuple(
        PositionBalance(key, kinds[key], money_round(amount)) for key, amount in balances.items()
    )
    nominal = money_round(net_worth(balances, kinds))
    real = money_round(nominal / inflation_index) if real_dollars else None
    return Observation(as_of, positions, nominal, inflation_index, real)
