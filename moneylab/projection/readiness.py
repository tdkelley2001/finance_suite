"""Execution-specific validation over structurally valid input snapshots."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from moneylab.configuration.models import AnalysisType
from moneylab.configuration.snapshot import ResolvedAnalysis
from moneylab.domain.planning import ActivityKind, Frequency, RecurringActivity, ScheduledAmountChange
from moneylab.domain.profile import (
    Access, Account, AccountKind, Asset, AssetClass, Liability, LiabilityKind, RateKind,
)
from moneylab.domain.values import Revision, decimal_sum

from .results import ExecutionIssue, MonthPeriod


METHODOLOGY = Revision("deterministic-monthly-projection", "1.0.0")
Position = Account | Asset | Liability


class ProjectionReadinessError(ValueError):
    """The recorded inputs require clarification or an unsupported methodology."""

    def __init__(self, issues: tuple[ExecutionIssue, ...]):
        self.issues = issues
        super().__init__(" | ".join(
            f"{issue.record_id}: {issue.message}" if issue.record_id else issue.message
            for issue in issues
        ))


@dataclass(frozen=True, slots=True)
class PreparedProjection:
    positions: dict[str, Position]
    opening: dict[str, Decimal]
    activities: tuple[RecurringActivity, ...]
    changes: dict[str, tuple[ScheduledAmountChange, ...]]


def month_boundary(start: date, months: int) -> date:
    years, month = divmod(start.month - 1 + months, 12)
    return date(start.year + years, month + 1, 1)


def _overlaps(activity: RecurringActivity, period: MonthPeriod) -> bool:
    return activity.start_on < period.end_before and (
        activity.end_before is None or activity.end_before > period.start_on
    )


def _references(activity: RecurringActivity) -> set[str]:
    return {
        key for key in (activity.from_account_id, activity.to_account_id, activity.liability_id)
        if key is not None
    }


def _check_position(position, valuation, members, growth, horizon, issues):
    parties = position.responsibility if isinstance(position, Liability) else position.ownership
    if not parties.person_ids() <= members:
        issues.append(ExecutionIssue("partial_ownership", "position crosses the analysis ownership boundary",
                                     position.id))
    if valuation.as_of != horizon.start_on:
        issues.append(ExecutionIssue(
            "unaligned_valuation",
            f"opening valuation dated {valuation.as_of} must be aligned to {horizon.start_on}",
            position.id,
        ))
    if not isinstance(position, Liability):
        if position.id not in growth:
            issues.append(ExecutionIssue("missing_growth", "supply an effective annual growth rate or zero",
                                         position.id))
        return
    if valuation.amount == 0:
        return
    terms = position.terms
    if (position.kind not in {LiabilityKind.MORTGAGE, LiabilityKind.INSTALLMENT_LOAN}
            or terms is None or terms.rate_kind is not RateKind.FIXED or terms.annual_rate is None):
        issues.append(ExecutionIssue(
            "unsupported_debt", "positive debt requires mortgage or installment terms with a fixed explicit rate",
            position.id,
        ))
        return
    maturity = terms.maturity_on
    if maturity is not None and maturity <= horizon.end_before:
        if maturity <= horizon.start_on or maturity.day != 1:
            issues.append(ExecutionIssue(
                "unsupported_maturity", "maturity within the horizon must be a month boundary after opening",
                position.id,
            ))


def _liquid_funding(account: Account, opening: Decimal) -> bool:
    holdings = account.holdings
    if any(holding.asset_class is not AssetClass.CASH for holding in holdings):
        return False
    if account.kind is AccountKind.DEPOSIT:
        return True
    if not holdings:
        return False
    if holdings[0].value is not None:
        return decimal_sum(holding.value.amount for holding in holdings) == opening
    return decimal_sum(holding.weight for holding in holdings) == 1


def _check_activity(activity, positions, effective, issues):
    if (activity.frequency is not Frequency.MONTHLY or activity.start_on.day != 1
            or (activity.end_before is not None and activity.end_before.day != 1)):
        issues.append(ExecutionIssue(
            "unsupported_schedule", "use monthly activity with first-of-month start and end boundaries",
            activity.id,
        ))
    if not _references(activity) <= positions.keys():
        issues.append(ExecutionIssue("cross_boundary_activity", "activity references a position outside scope",
                                     activity.id))
    source = activity.from_account_id
    if activity.kind is ActivityKind.EXTERNAL_INCOME:
        if activity.to_account_id is None:
            issues.append(ExecutionIssue("missing_destination", "income requires a destination account",
                                         activity.id))
    elif source is None:
        issues.append(ExecutionIssue("missing_funding_account", "activity requires a funding account",
                                     activity.id))
    elif source in positions:
        account = positions[source]
        if account.access is not Access.UNRESTRICTED:
            issues.append(ExecutionIssue(
                "restricted_funding", f"debit account {source} needs explicit unrestricted access",
                activity.id,
            ))
        elif not _liquid_funding(account, effective[source].amount):
            issues.append(ExecutionIssue(
                "noncash_funding", f"debit account {source} needs a modeled deposit or a fully disclosed cash balance",
                activity.id,
            ))


def _schedule(snapshot, positions, effective, horizon, issues):
    plan = snapshot.plan
    if plan is None:
        return (), {}
    selected = {activity.id for activity in plan.activities_for(snapshot.profile, snapshot.request.inputs.subject)}
    activities = []
    payments = {}
    for activity in plan.activities:
        if not _overlaps(activity, horizon):
            continue
        if activity.id not in selected:
            if _references(activity) & positions.keys():
                issues.append(ExecutionIssue(
                    "out_of_scope_activity", "activity assigned outside the subject affects an in-scope position",
                    activity.id,
                ))
            continue
        _check_activity(activity, positions, effective, issues)
        activities.append(activity)
        if activity.kind is ActivityKind.DEBT_PAYMENT:
            payments.setdefault(activity.liability_id, []).append(activity)

    for liability_id, schedules in payments.items():
        last_end = horizon.start_on
        for activity in sorted(schedules, key=lambda item: item.start_on):
            effective_start = max(activity.start_on, horizon.start_on)
            if effective_start < last_end:
                issues.append(ExecutionIssue("competing_debt_payments", "loan payment schedules overlap",
                                             liability_id))
                break
            last_end = min(activity.end_before or horizon.end_before, horizon.end_before)

    active_ids = {activity.id for activity in activities}
    changes = {}
    for change in sorted(plan.changes, key=lambda item: item.effective_on):
        if change.activity_id in active_ids and change.effective_on < horizon.end_before:
            if change.effective_on.day != 1:
                issues.append(ExecutionIssue(
                    "unsupported_change_date", "scheduled amount changes must start on the first of a month",
                    change.id,
                ))
            changes.setdefault(change.activity_id, []).append(change)
    return tuple(activities), {key: tuple(entries) for key, entries in changes.items()}


def prepare(snapshot: ResolvedAnalysis) -> PreparedProjection:
    if (not isinstance(snapshot, ResolvedAnalysis)
            or snapshot.request.analysis_type is not AnalysisType.MONTHLY_PROJECTION):
        raise ProjectionReadinessError((ExecutionIssue("analysis_type", "expected a monthly projection snapshot"),))
    if snapshot.request.stochastic is not None:
        raise ProjectionReadinessError((ExecutionIssue("stochastic", "this methodology is deterministic"),))
    if snapshot.request.methodology not in (None, METHODOLOGY):
        raise ProjectionReadinessError((ExecutionIssue("methodology", "requested methodology differs from M03"),))

    inputs = snapshot.request.inputs
    profile = snapshot.profile
    try:
        horizon = MonthPeriod(inputs.start_on, month_boundary(inputs.start_on, snapshot.preferences.horizon_months))
    except (ValueError, OverflowError) as exc:
        raise ProjectionReadinessError((ExecutionIssue("horizon", "horizon extends beyond the calendar range"),)) from exc
    positions = {item.id: item for item in profile.positions_for(inputs.subject)}
    effective = snapshot.opening_valuations()
    members = profile.people_in(inputs.subject)
    growth = {entry.position_id for entry in snapshot.position_growth}
    issues = []
    for key, position in positions.items():
        _check_position(position, effective[key], members, growth, horizon, issues)
    activities, changes = _schedule(snapshot, positions, effective, horizon, issues)
    if issues:
        raise ProjectionReadinessError(tuple(issues))
    return PreparedProjection(positions, {key: value.amount for key, value in effective.items()},
                              activities, changes)
