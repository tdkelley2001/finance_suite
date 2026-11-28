"""Validated policy inputs for future portfolio execution."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from moneylab.domain.values import Revision, Source, SourceKind, decimal_value, identifier, validate_source

from .allocation import Allocation, ONE


class ContributionKind(str, Enum):
    TARGET = "target"
    CURRENT = "current"
    REBALANCE_DIRECTED = "rebalance_directed"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ContributionPolicy:
    kind: ContributionKind
    custom: Allocation | None = None
    zero_balance_fallback: Allocation | None = None

    def __post_init__(self):
        if not isinstance(self.kind, ContributionKind):
            raise ValueError("expected a contribution method")
        if (self.kind is ContributionKind.CUSTOM) != isinstance(self.custom, Allocation):
            raise ValueError("only custom contributions require custom weights")
        if self.custom is not None and not isinstance(self.custom, Allocation):
            raise ValueError("expected allocation weights")
        if self.zero_balance_fallback is not None and (
            self.kind is not ContributionKind.CURRENT or not isinstance(self.zero_balance_fallback, Allocation)
        ):
            raise ValueError("only current-allocation contributions accept a zero-balance fallback")


class WithdrawalKind(str, Enum):
    PROPORTIONAL = "proportional"
    REBALANCE_DIRECTED = "rebalance_directed"
    CASH_FIRST = "cash_first"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class WithdrawalPolicy:
    kind: WithdrawalKind
    custom: Allocation | None = None
    cash_sleeve_id: str | None = None
    secondary: WithdrawalPolicy | None = None

    def __post_init__(self):
        if not isinstance(self.kind, WithdrawalKind):
            raise ValueError("expected a withdrawal method")
        if (self.kind is WithdrawalKind.CUSTOM) != isinstance(self.custom, Allocation):
            raise ValueError("only custom withdrawals require custom weights")
        if self.custom is not None and not isinstance(self.custom, Allocation):
            raise ValueError("expected allocation weights")
        if self.kind is WithdrawalKind.CASH_FIRST:
            identifier(self.cash_sleeve_id)
            if not isinstance(self.secondary, WithdrawalPolicy) or self.secondary.kind is WithdrawalKind.CASH_FIRST:
                raise ValueError("cash-first withdrawals require a non-cash-first secondary policy")
        elif self.cash_sleeve_id is not None or self.secondary is not None:
            raise ValueError("cash sleeve and secondary policy apply only to cash-first withdrawals")

    def rules(self) -> tuple[WithdrawalPolicy, ...]:
        return (self,) if self.secondary is None else (self, self.secondary)


class DriftBasis(str, Enum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"


class ZeroTargetRule(str, Enum):
    ANY_POSITIVE = "any_positive"
    ABSOLUTE = "absolute"


@dataclass(frozen=True, slots=True)
class DriftThreshold:
    basis: DriftBasis
    fraction: Decimal
    zero_target: ZeroTargetRule | None = None
    zero_target_fraction: Decimal | None = None

    def __post_init__(self):
        if not isinstance(self.basis, DriftBasis):
            raise ValueError("expected an absolute or relative drift basis")
        decimal_value(self.fraction, minimum=0)
        if not self.fraction or (self.basis is DriftBasis.ABSOLUTE and self.fraction > ONE):
            raise ValueError("drift thresholds must be positive and absolute thresholds cannot exceed one")
        if self.zero_target is not None and (
            self.basis is not DriftBasis.RELATIVE or not isinstance(self.zero_target, ZeroTargetRule)
        ):
            raise ValueError("only relative drift can specify a zero-target rule")
        if self.zero_target is ZeroTargetRule.ABSOLUTE:
            decimal_value(self.zero_target_fraction, minimum=0)
            if not 0 < self.zero_target_fraction <= ONE:
                raise ValueError("zero-target absolute threshold must be in (0, 1]")
        elif self.zero_target_fraction is not None:
            raise ValueError("zero-target threshold requires the absolute zero-target rule")


class RebalanceKind(str, Enum):
    NONE = "none"
    CALENDAR = "calendar"
    THRESHOLD = "threshold"
    CALENDAR_OR_THRESHOLD = "calendar_or_threshold"
    THRESHOLD_ON_SCHEDULE = "threshold_on_schedule"


@dataclass(frozen=True, slots=True)
class RebalancePolicy:
    kind: RebalanceKind = RebalanceKind.NONE
    calendar_months: tuple[int, ...] = ()
    threshold: DriftThreshold | None = None

    def __post_init__(self):
        if not isinstance(self.kind, RebalanceKind):
            raise ValueError("expected an explicit rebalancing trigger")
        months = tuple(self.calendar_months)
        if any(type(month) is not int or not 1 <= month <= 12 for month in months) or len(set(months)) != len(months):
            raise ValueError("calendar months must be unique integers from 1 through 12")
        if bool(months) != (self.kind in {
            RebalanceKind.CALENDAR, RebalanceKind.CALENDAR_OR_THRESHOLD, RebalanceKind.THRESHOLD_ON_SCHEDULE,
        }):
            raise ValueError("calendar months must match the selected rebalancing trigger")
        if (self.threshold is not None) != (self.kind in {
            RebalanceKind.THRESHOLD, RebalanceKind.CALENDAR_OR_THRESHOLD, RebalanceKind.THRESHOLD_ON_SCHEDULE,
        }):
            raise ValueError("drift threshold must match the selected rebalancing trigger")
        if self.threshold is not None and not isinstance(self.threshold, DriftThreshold):
            raise ValueError("expected a drift threshold")
        object.__setattr__(self, "calendar_months", tuple(sorted(months)))


@dataclass(frozen=True, slots=True)
class InvestmentPolicy:
    revision: Revision
    target: Allocation | None = None
    contribution: ContributionPolicy | None = None
    withdrawal: WithdrawalPolicy | None = None
    rebalance: RebalancePolicy = RebalancePolicy()
    source: Source | None = None

    def __post_init__(self):
        if not isinstance(self.revision, Revision) or not isinstance(self.rebalance, RebalancePolicy):
            raise ValueError("investment policy requires a revision and rebalancing trigger")
        validate_source(self.source, SourceKind.USER_PLAN)
        for value, expected in (
            (self.target, Allocation), (self.contribution, ContributionPolicy), (self.withdrawal, WithdrawalPolicy),
        ):
            if value is not None and not isinstance(value, expected):
                raise ValueError(f"expected {expected.__name__}")

        contribution = self.contribution.kind if self.contribution is not None else None
        withdrawal_rules = self.withdrawal.rules() if self.withdrawal is not None else ()
        uses_target = (
            contribution in {ContributionKind.TARGET, ContributionKind.REBALANCE_DIRECTED}
            or any(rule.kind is WithdrawalKind.REBALANCE_DIRECTED for rule in withdrawal_rules)
            or self.rebalance.kind is not RebalanceKind.NONE
        )
        if uses_target and self.target is None:
            raise ValueError("the selected investment policy requires target weights")
        threshold = self.rebalance.threshold
        if (threshold is not None and threshold.basis is DriftBasis.RELATIVE
                and any(weight.weight == 0 for weight in self.target.weights)
                and threshold.zero_target is None):
            raise ValueError("relative drift requires an explicit rule for zero-target sleeves")

    def validate_destinations(self, sleeve_ids: set[str], cash_sleeve_ids: set[str]) -> None:
        allocations = [self.target]
        if self.contribution is not None:
            allocations.extend((self.contribution.custom, self.contribution.zero_balance_fallback))
        if self.withdrawal is not None:
            for rule in self.withdrawal.rules():
                allocations.append(rule.custom)
                if rule.kind is WithdrawalKind.CASH_FIRST:
                    if rule.cash_sleeve_id not in cash_sleeve_ids:
                        raise ValueError("cash-first requires an explicitly cash-exposed sleeve")
                    if rule.secondary.custom is not None and any(
                        item.sleeve_id == rule.cash_sleeve_id and item.weight
                        for item in rule.secondary.custom.weights
                    ):
                        raise ValueError("cash-first secondary weights cannot debit the depleted cash sleeve")
        for allocation in allocations:
            if allocation is not None:
                allocation.require_destinations(sleeve_ids)
