"""Execute complete months with all-or-nothing funding and explicit postings."""

from dataclasses import dataclass, replace
from decimal import Decimal, localcontext

from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.planning import ActivityKind, RecurringActivity
from moneylab.domain.profile import Account, Liability

from .accounting import (
    CALCULATION_CONTEXT, ONE, ZERO, money_round, monthly_effective_rate, observe, reconcile,
)
from .debt import quote_debt
from .readiness import METHODOLOGY, month_boundary, prepare
from .results import (
    EffectKind, FinancialEffect, FundingShortfall, MonthPeriod, MonthResult, PlannedAmount,
    PositionKind, Posting, ProjectionResult, ProjectionStatus, Termination,
)


@dataclass(frozen=True, slots=True)
class _Debit:
    activity: RecurringActivity
    amount: Decimal
    effects: tuple[FinancialEffect, ...]


_MOVEMENT_KINDS = {
    ActivityKind.TRANSFER: EffectKind.TRANSFER,
    ActivityKind.CONTRIBUTION: EffectKind.CONTRIBUTION,
    ActivityKind.WITHDRAWAL: EffectKind.WITHDRAWAL,
}


def _active_activities(prepared, period):
    for activity in prepared.activities:
        if activity.start_on > period.start_on or (
            activity.end_before is not None and activity.end_before <= period.start_on
        ):
            continue
        for change in reversed(prepared.changes.get(activity.id, ())):
            if change.effective_on <= period.start_on:
                activity = replace(activity, amount=change.new_amount)
                break
        yield activity


def _accrue_growth(opening, kinds, monthly_rates):
    balances = dict(opening)
    effects = []
    for position_id, rate in monthly_rates.items():
        gain = money_round(opening[position_id] * rate)
        if gain:
            balances[position_id] += gain
            kind = (EffectKind.ACCOUNT_RETURN if kinds[position_id] is PositionKind.ACCOUNT
                    else EffectKind.ASSET_REVALUATION)
            effects.append(FinancialEffect(kind, gain, (Posting(position_id, gain),)))
    return balances, effects


def _activity_effects(activities, available):
    income = []
    debits = []
    debt_payments = {}
    for activity in activities:
        amount = activity.amount.amount
        if activity.kind is ActivityKind.DEBT_PAYMENT:
            debt_payments[activity.liability_id] = activity
        elif not amount:
            continue
        elif activity.kind is ActivityKind.EXTERNAL_INCOME:
            available[activity.to_account_id] += amount
            income.append(FinancialEffect(
                EffectKind.INCOME, amount, (Posting(activity.to_account_id, amount),), activity.id,
            ))
        else:
            postings = (Posting(activity.from_account_id, -amount),)
            kind = EffectKind.EXPENSE
            if activity.kind in _MOVEMENT_KINDS:
                kind = _MOVEMENT_KINDS[activity.kind]
                postings += (Posting(activity.to_account_id, amount),)
            effect = FinancialEffect(kind, amount, postings, activity.id)
            debits.append(_Debit(activity, amount, (effect,)))
    return income, debits, debt_payments


def _funding_shortfalls(available, debits):
    accounts = {}
    for debit in debits:
        accounts.setdefault(debit.activity.from_account_id, []).append(
            PlannedAmount(debit.activity.id, debit.amount)
        )
    shortfalls = []
    for account_id, charges in sorted(accounts.items()):
        required = sum((item.amount for item in charges), start=ZERO)
        balance = available[account_id]
        if required > balance:
            shortfalls.append(FundingShortfall(
                account_id, balance, required, required - balance,
                tuple(sorted(charges, key=lambda item: item.activity_id)),
            ))
    return tuple(shortfalls)


def _execute_month(prepared, period, opening, kinds, monthly_rates, inflation_index, real_dollars):
    activities = tuple(_active_activities(prepared, period))
    available, growth = _accrue_growth(opening, kinds, monthly_rates)
    income, debits, debt_payments = _activity_effects(activities, available)

    liabilities = {}
    issues = []
    debt_accruals = []
    for position_id, position in prepared.positions.items():
        if not isinstance(position, Liability):
            continue
        payment = debt_payments.get(position_id)
        quote = quote_debt(position, opening[position_id], payment, period)
        if quote.issue is not None:
            issues.append(quote.issue)
            continue
        liabilities[position_id] = quote.closing
        for effect in quote.effects:
            if effect.kind is EffectKind.INTEREST_ACCRUED:
                debt_accruals.append(effect)
        if quote.payment:
            debits.append(_Debit(payment, quote.payment, tuple(
                effect for effect in quote.effects if effect.kind is not EffectKind.INTEREST_ACCRUED
            )))

    shortfalls = _funding_shortfalls(available, debits) if not issues else ()
    if issues or shortfalls:
        planned = tuple(PlannedAmount(activity.id, activity.amount.amount) for activity in activities)
        return Termination(period, planned, tuple(issues), shortfalls)

    # Test funding against the aggregate before adding internal receipts. Build
    # closing balances independently of the postings used for reconciliation.
    closing = dict(available)
    closing.update(liabilities)
    for debit in debits:
        activity = debit.activity
        closing[activity.from_account_id] -= debit.amount
        if activity.to_account_id is not None:
            closing[activity.to_account_id] += debit.amount
    # The ledger presents accruals before end-of-month income and settlements.
    ledger = (*growth, *debt_accruals, *income,
              *(effect for debit in debits for effect in debit.effects))
    reconciliation = reconcile(opening, closing, kinds, ledger)
    observation = observe(period.end_before, closing, kinds, inflation_index, real_dollars)
    return MonthResult(period, observation, ledger, reconciliation), closing


def project_monthly(snapshot: ResolvedAnalysis) -> ProjectionResult:
    """Execute M03, returning the last committed observation on a modeled stop."""
    prepared = prepare(snapshot)
    with localcontext(CALCULATION_CONTEXT):
        monthly_rates = {
            item.position_id: monthly_effective_rate(item.annual_effective_rate)
            for item in snapshot.position_growth
        }
        inflation = snapshot.assumptions.annual_inflation
        inflation_factor = ONE + monthly_effective_rate(inflation) if inflation is not None else None
        index = ONE if inflation_factor is not None else None
        real_dollars = snapshot.preferences.use_real_dollars is True
        inputs = snapshot.request.inputs
        horizon = snapshot.preferences.horizon_months
        kinds = {
            key: (PositionKind.LIABILITY if isinstance(position, Liability) else
                  PositionKind.ACCOUNT if isinstance(position, Account) else PositionKind.ASSET)
            for key, position in prepared.positions.items()
        }
        balances = prepared.opening
        initial = observe(inputs.start_on, balances, kinds, index, real_dollars)
        months = []
        termination = None
        for offset in range(horizon):
            period = MonthPeriod(month_boundary(inputs.start_on, offset),
                                 month_boundary(inputs.start_on, offset + 1))
            if inflation_factor is not None:
                index *= inflation_factor
            executed = _execute_month(prepared, period, balances, kinds, monthly_rates, index, real_dollars)
            if isinstance(executed, Termination):
                termination = executed
                break
            month, balances = executed
            months.append(month)
        return ProjectionResult(
            input_content_id=snapshot.content_id, methodology=METHODOLOGY,
            currency=snapshot.profile.currency, subject=inputs.subject, requested_months=horizon,
            completed_months=len(months),
            status=ProjectionStatus.COMPLETED if termination is None else ProjectionStatus.STOPPED,
            opening=initial, months=tuple(months), annual_inflation=inflation,
            position_growth=snapshot.position_growth, termination=termination,
        )
