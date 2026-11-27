"""Financial intent, kept separately from the current financial position."""

from dataclasses import dataclass
from datetime import date
from enum import Enum

from .profile import FinancialProfile, Subject, SubjectKind
from .values import (
    Money,
    Revision,
    Source,
    SourceKind,
    calendar_date,
    decimal_sum,
    distinct_ids,
    distinct_records,
    identifier,
    validate_source,
)


class Frequency(str, Enum):
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"
    ANNUALLY = "annually"


class ActivityKind(str, Enum):
    EXTERNAL_INCOME = "external_income"
    EXTERNAL_EXPENSE = "external_expense"
    TRANSFER = "transfer"
    CONTRIBUTION = "contribution"
    WITHDRAWAL = "withdrawal"
    DEBT_PAYMENT = "debt_payment"


def nonnegative_money(value: Money) -> None:
    if not isinstance(value, Money) or value.amount < 0:
        raise ValueError("expected nonnegative money")


@dataclass(frozen=True, slots=True)
class DebtPaymentSplit:
    principal: Money
    interest: Money

    def __post_init__(self):
        nonnegative_money(self.principal)
        nonnegative_money(self.interest)
        self.interest.require_currency(self.principal.currency)


@dataclass(frozen=True, slots=True)
class RecurringActivity:
    id: str
    name: str
    kind: ActivityKind
    subject: Subject
    amount: Money
    frequency: Frequency
    start_on: date
    end_before: date | None = None
    from_account_id: str | None = None
    to_account_id: str | None = None
    liability_id: str | None = None
    debt_split: DebtPaymentSplit | None = None
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.name)
        if (not isinstance(self.kind, ActivityKind)
                or not isinstance(self.subject, Subject)
                or not isinstance(self.frequency, Frequency)):
            raise ValueError("activity requires a kind, subject and frequency")
        nonnegative_money(self.amount)
        calendar_date(self.start_on)
        if self.end_before is not None:
            calendar_date(self.end_before)
            if self.end_before <= self.start_on:
                raise ValueError("activity end must follow its start")
        validate_source(self.source, SourceKind.USER_PLAN)

        for reference in (self.from_account_id, self.to_account_id, self.liability_id):
            if reference is not None:
                identifier(reference)
        if self.kind is ActivityKind.DEBT_PAYMENT:
            if self.liability_id is None or self.to_account_id is not None:
                raise ValueError("debt payment requires a liability as destination")
            if self.debt_split is not None:
                if not isinstance(self.debt_split, DebtPaymentSplit):
                    raise ValueError("expected a principal/interest split")
                self.debt_split.principal.require_currency(self.amount.currency)
                total = decimal_sum((self.debt_split.principal.amount, self.debt_split.interest.amount))
                if total != self.amount.amount:
                    raise ValueError("debt payment must equal principal plus interest")
            return

        if self.liability_id is not None or self.debt_split is not None:
            raise ValueError("liability and debt split apply only to debt payments")
        if self.kind is ActivityKind.EXTERNAL_INCOME:
            if self.from_account_id is not None:
                raise ValueError("external income cannot originate in a tracked account")
        elif self.kind is ActivityKind.EXTERNAL_EXPENSE:
            if self.to_account_id is not None:
                raise ValueError("external expense cannot go to a tracked account")
        elif (self.from_account_id is None or self.to_account_id is None
                or self.from_account_id == self.to_account_id):
            raise ValueError("internal movement requires two distinct accounts")


@dataclass(frozen=True, slots=True)
class Goal:
    id: str
    name: str
    subject: Subject
    target_amount: Money
    target_on: date
    funding_account_ids: tuple[str, ...] = ()
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.name)
        if not isinstance(self.subject, Subject):
            raise ValueError("expected a goal subject")
        nonnegative_money(self.target_amount)
        calendar_date(self.target_on)
        validate_source(self.source, SourceKind.USER_PLAN)
        object.__setattr__(self, "funding_account_ids", distinct_ids(self.funding_account_ids))


@dataclass(frozen=True, slots=True)
class ScheduledAmountChange:
    id: str
    activity_id: str
    effective_on: date
    new_amount: Money
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.activity_id)
        calendar_date(self.effective_on)
        nonnegative_money(self.new_amount)
        validate_source(self.source, SourceKind.USER_PLAN)


@dataclass(frozen=True, slots=True)
class FinancialPlan:
    revision: Revision
    profile_id: str
    activities: tuple[RecurringActivity, ...] = ()
    goals: tuple[Goal, ...] = ()
    changes: tuple[ScheduledAmountChange, ...] = ()
    source: Source | None = None

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("expected a plan revision")
        identifier(self.profile_id)
        validate_source(self.source, SourceKind.USER_PLAN)
        for field, record_type in (
            ("activities", RecurringActivity), ("goals", Goal), ("changes", ScheduledAmountChange),
        ):
            object.__setattr__(self, field, distinct_records(getattr(self, field), record_type))

        activities = {activity.id: activity for activity in self.activities}
        scheduled_dates = set()
        for change in self.changes:
            activity = activities.get(change.activity_id)
            if activity is None or activity.kind not in {
                ActivityKind.EXTERNAL_INCOME, ActivityKind.EXTERNAL_EXPENSE,
            }:
                raise ValueError("scheduled changes require an existing income or expense")
            change.new_amount.require_currency(activity.amount.currency)
            if (change.effective_on < activity.start_on
                    or (activity.end_before is not None
                        and change.effective_on >= activity.end_before)):
                raise ValueError("scheduled change must fall within the activity period")
            key = (change.activity_id, change.effective_on)
            if key in scheduled_dates:
                raise ValueError("an activity can have only one change on a date")
            scheduled_dates.add(key)

    def validate_against(self, profile: FinancialProfile) -> None:
        if self.profile_id != profile.revision.id:
            raise ValueError(f"plan requires profile {self.profile_id}")
        accounts = {account.id: account for account in profile.accounts}
        liabilities = {liability.id: liability for liability in profile.liabilities}
        for activity in self.activities:
            people = profile.people_in(activity.subject)
            activity.amount.require_currency(profile.currency)
            for account_id in (activity.from_account_id, activity.to_account_id):
                if account_id is not None and (
                    account_id not in accounts or not people & accounts[account_id].ownership.person_ids()
                ):
                    raise ValueError(f"{activity.id} references an unknown or out-of-scope account")
            if activity.liability_id is not None:
                debt = liabilities.get(activity.liability_id)
                if debt is None or not people & debt.responsibility.person_ids():
                    raise ValueError(f"{activity.id} references an unknown or out-of-scope liability")
        for goal in self.goals:
            people = profile.people_in(goal.subject)
            goal.target_amount.require_currency(profile.currency)
            for account_id in goal.funding_account_ids:
                if account_id not in accounts or not people & accounts[account_id].ownership.person_ids():
                    raise ValueError(f"{goal.id} references an unknown or out-of-scope funding account")

    def activities_for(self, profile: FinancialProfile, subject: Subject) -> tuple[RecurringActivity, ...]:
        people = profile.people_in(subject)
        return tuple(
            activity for activity in self.activities
            if activity.subject == subject
            or (subject.kind is SubjectKind.HOUSEHOLD and activity.subject.kind is SubjectKind.PERSON
                and activity.subject.id in people)
        )
