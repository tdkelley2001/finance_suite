"""Deterministic rate conversion, postings and reconciliation."""

from decimal import Decimal, Overflow, localcontext

from moneylab.economics.rates import CALCULATION_CONTEXT

from .results import (
    EffectKind, FinancialEffect, Observation, PositionBalance, PositionKind, Reconciliation,
)


ZERO = Decimal(0)
MONEY_QUANTUM = Decimal("0.00000001")
AMOUNT_LIMIT = Decimal("1e30")


class ProjectionRangeError(ArithmeticError):
    """A calculated amount exceeds the supported numerical range."""


class ReconciliationError(ArithmeticError):
    """Projected closing positions disagree with recorded financial effects."""


def money_round(amount: Decimal, *, field: str = "projection amount") -> Decimal:
    if not amount.is_finite() or amount.copy_abs() >= AMOUNT_LIMIT:
        raise ProjectionRangeError(f"{field} must be finite and below 10^30 in magnitude")
    rounded = amount.quantize(MONEY_QUANTUM)
    if rounded.copy_abs() >= AMOUNT_LIMIT:
        raise ProjectionRangeError(f"{field} rounds beyond the projection amount limit")
    return rounded


def advance_inflation_index(index: Decimal, monthly_factor: Decimal) -> Decimal:
    try:
        advanced = index * monthly_factor
    except Overflow as exc:
        raise ProjectionRangeError("inflation index overflowed") from exc
    if not advanced.is_finite() or advanced <= ZERO:
        raise ProjectionRangeError("inflation index must remain finite and positive")
    return advanced


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
        PositionBalance(key, kinds[key], money_round(amount, field=f"balance for {key}"))
        for key, amount in balances.items()
    )
    nominal = money_round(net_worth(balances, kinds), field="nominal net worth")
    real = None
    if real_dollars:
        try:
            deflated = nominal / inflation_index
        except Overflow as exc:
            raise ProjectionRangeError("real net worth overflowed") from exc
        real = money_round(deflated, field="real net worth")
    return Observation(as_of, positions, nominal, inflation_index, real)
