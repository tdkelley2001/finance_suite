"""Fixed-rate servicing and payoff quotes for a single month."""

from dataclasses import dataclass
from decimal import Decimal

from moneylab.domain.planning import RecurringActivity
from moneylab.domain.profile import Liability

from .accounting import ZERO, money_round
from .results import EffectKind, ExecutionIssue, FinancialEffect, MonthPeriod, Posting


@dataclass(frozen=True, slots=True)
class DebtQuote:
    closing: Decimal
    payment: Decimal = ZERO
    effects: tuple[FinancialEffect, ...] = ()
    issue: ExecutionIssue | None = None


def quote_debt(
    liability: Liability, opening: Decimal, activity: RecurringActivity | None, period: MonthPeriod,
) -> DebtQuote:
    if not opening:
        return DebtQuote(ZERO)

    interest = money_round(opening * liability.terms.annual_rate / 12)
    if activity is None and interest:
        return DebtQuote(opening, issue=ExecutionIssue(
            "missing_debt_payment", "supply an active payment covering accrued interest",
            liability.id, interest,
        ))

    planned = activity.amount.amount if activity is not None else ZERO
    payment = min(planned, opening + interest)
    if payment < interest:
        return DebtQuote(opening, issue=ExecutionIssue(
            "payment_below_interest", "planned payment does not cover current interest",
            activity.id, interest - payment,
        ))
    principal = payment - interest
    split = activity.debt_split if activity is not None else None
    if split is not None and (split.principal.amount != principal or split.interest.amount != interest):
        return DebtQuote(opening, issue=ExecutionIssue(
            "payment_split_mismatch", "supplied principal and interest split differs from the fixed-rate calculation",
            activity.id,
        ))
    closing = opening - principal
    if liability.terms.maturity_on == period.end_before and closing:
        return DebtQuote(opening, issue=ExecutionIssue(
            "maturity_balance", "scheduled payment leaves debt outstanding at maturity", liability.id, closing,
        ))

    if activity is None:
        return DebtQuote(closing)

    effects = []
    if interest:
        effects.extend((
            FinancialEffect(EffectKind.INTEREST_ACCRUED, interest, (Posting(liability.id, interest),)),
            FinancialEffect(
                EffectKind.INTEREST_PAID, interest,
                (Posting(activity.from_account_id, -interest), Posting(liability.id, -interest)),
                activity.id,
            ),
        ))
    if principal:
        effects.append(FinancialEffect(
            EffectKind.PRINCIPAL_PAID, principal,
            (Posting(activity.from_account_id, -principal), Posting(liability.id, -principal)),
            activity.id,
        ))
    return DebtQuote(closing, payment, tuple(effects))
