"""Investment plans and scoped, typed configuration layers."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from moneylab.domain.values import Revision, Source, SourceKind, distinct_records, identifier, validate_source

from .allocation import Allocation
from .exposures import ReturnTreatment, annual_fee
from .policy import InvestmentPolicy


@dataclass(frozen=True, slots=True)
class SecurityIdentity:
    namespace: str
    identifier: str

    def __post_init__(self):
        identifier(self.namespace)
        identifier(self.identifier)


@dataclass(frozen=True, slots=True)
class Investment:
    id: str
    name: str
    security: SecurityIdentity | None = None
    treatment: ReturnTreatment | None = None
    annual_fund_expense: Decimal | None = None
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.name)
        if self.security is not None and not isinstance(self.security, SecurityIdentity):
            raise ValueError("expected a namespaced security identity")
        if self.treatment is not None and not isinstance(self.treatment, ReturnTreatment):
            raise ValueError("expected an explicit investment return treatment")
        annual_fee(self.annual_fund_expense)
        validate_source(self.source, SourceKind.USER_PLAN)


@dataclass(frozen=True, slots=True)
class Sleeve:
    id: str
    investment_id: str
    holding_id: str | None = None
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.investment_id)
        if self.holding_id is not None:
            identifier(self.holding_id)
        validate_source(self.source, SourceKind.USER_PLAN)


class InvestmentMode(str, Enum):
    AGGREGATE = "aggregate"
    DETAILED = "detailed"


@dataclass(frozen=True, slots=True)
class AccountInvestmentPlan:
    account_id: str
    mode: InvestmentMode
    sleeves: tuple[Sleeve, ...] = ()
    residual_sleeve_id: str | None = None
    aggregate_return: ReturnTreatment | None = None
    annual_advisory_fee: Decimal | None = None
    policy: InvestmentPolicy | None = None
    source: Source | None = None

    def __post_init__(self):
        identifier(self.account_id)
        if not isinstance(self.mode, InvestmentMode):
            raise ValueError("select an explicit account investment mode")
        annual_fee(self.annual_advisory_fee)
        validate_source(self.source, SourceKind.USER_PLAN)
        sleeves = distinct_records(self.sleeves, Sleeve)
        object.__setattr__(self, "sleeves", sleeves)
        if self.mode is InvestmentMode.AGGREGATE:
            if sleeves or self.residual_sleeve_id is not None or self.policy is not None:
                raise ValueError("aggregate treatments cannot include sleeves or sleeve policies")
            if self.aggregate_return is not None and not isinstance(self.aggregate_return, ReturnTreatment):
                raise ValueError("expected an aggregate return treatment")
            return
        if not sleeves or self.aggregate_return is not None:
            raise ValueError("detailed plans require sleeves and cannot include an aggregate treatment")
        if self.policy is not None and not isinstance(self.policy, InvestmentPolicy):
            raise ValueError("expected an investment policy")
        links = [sleeve.holding_id for sleeve in sleeves if sleeve.holding_id is not None]
        if len(set(links)) != len(links):
            raise ValueError("a reported holding cannot supply more than one sleeve")
        if self.residual_sleeve_id is not None:
            identifier(self.residual_sleeve_id)
            residual = next((sleeve for sleeve in sleeves if sleeve.id == self.residual_sleeve_id), None)
            if residual is None or residual.holding_id is not None:
                raise ValueError("residual treatment requires a dedicated sleeve without a reported holding")


@dataclass(frozen=True, slots=True)
class InvestmentPlan:
    revision: Revision
    profile_id: str
    accounts: tuple[AccountInvestmentPlan, ...]
    investments: tuple[Investment, ...] = ()

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("investment plan requires a revision")
        identifier(self.profile_id)
        accounts = distinct_records(self.accounts, AccountInvestmentPlan, key=lambda item: item.account_id)
        investments = distinct_records(self.investments, Investment)
        if not accounts:
            raise ValueError("investment plan requires at least one account")
        used = {sleeve.investment_id for account in accounts for sleeve in account.sleeves}
        if not used <= {item.id for item in investments}:
            raise ValueError("modeled sleeves must reference known investments")
        object.__setattr__(self, "accounts", accounts)
        object.__setattr__(self, "investments", investments)


class ReturnTarget(str, Enum):
    ACCOUNT = "account"
    INVESTMENT = "investment"


@dataclass(frozen=True, slots=True)
class ReturnOverride:
    target: ReturnTarget
    id: str
    treatment: ReturnTreatment

    def __post_init__(self):
        identifier(self.id)
        if not isinstance(self.target, ReturnTarget) or not isinstance(self.treatment, ReturnTreatment):
            raise ValueError("return override requires a target category and treatment")


def capture_returns(returns):
    return distinct_records(returns, ReturnOverride, key=lambda item: (item.target.value, item.id))


@dataclass(frozen=True, slots=True)
class AccountInvestmentOverride:
    account_id: str
    allocation: Allocation | None = None
    policy: InvestmentPolicy | None = None

    def __post_init__(self):
        identifier(self.account_id)
        if self.allocation is None and self.policy is None:
            raise ValueError("investment override requires an allocation or policy")
        if self.allocation is not None and not isinstance(self.allocation, Allocation):
            raise ValueError("expected hypothetical allocation weights")
        if self.policy is not None and not isinstance(self.policy, InvestmentPolicy):
            raise ValueError("expected an investment policy")


@dataclass(frozen=True, slots=True)
class InvestmentOverrides:
    accounts: tuple[AccountInvestmentOverride, ...] = ()
    returns: tuple[ReturnOverride, ...] = ()

    def __post_init__(self):
        accounts = distinct_records(self.accounts, AccountInvestmentOverride, key=lambda item: item.account_id)
        object.__setattr__(self, "accounts", accounts)
        object.__setattr__(self, "returns", capture_returns(self.returns))


@dataclass(frozen=True, slots=True)
class InvestmentScenario:
    scenario_revision: Revision
    plan_id: str
    overrides: InvestmentOverrides

    def __post_init__(self):
        identifier(self.plan_id)
        if not isinstance(self.scenario_revision, Revision) or not isinstance(self.overrides, InvestmentOverrides):
            raise ValueError("investment scenario requires a financial scenario revision and typed overrides")


@dataclass(frozen=True, slots=True)
class InvestmentReturnPreset:
    """An explicit return-only input layer, also usable as research defaults."""

    revision: Revision
    returns: tuple[ReturnOverride, ...]

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("investment return presets require a revision")
        object.__setattr__(self, "returns", capture_returns(self.returns))
