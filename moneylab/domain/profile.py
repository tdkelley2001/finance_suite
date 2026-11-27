"""People, ownership and authoritative financial position records."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from .values import (
    Money,
    Revision,
    Source,
    SourceKind,
    Valuation,
    calendar_date,
    currency_code,
    decimal_sum,
    decimal_value,
    distinct_ids,
    distinct_records,
    identifier,
    validate_source,
)


@dataclass(frozen=True, slots=True)
class Person:
    id: str
    name: str
    birth_date: date | None = None
    source: Source | None = None

    def __post_init__(self):
        identifier(self.id)
        identifier(self.name)
        if self.birth_date is not None:
            calendar_date(self.birth_date)
        validate_source(self.source, SourceKind.USER_FACT)


@dataclass(frozen=True, slots=True)
class Household:
    id: str
    name: str
    member_ids: tuple[str, ...]

    def __post_init__(self):
        identifier(self.id)
        identifier(self.name)
        members = distinct_ids(self.member_ids)
        if not members:
            raise ValueError("a household requires at least one person")
        object.__setattr__(self, "member_ids", members)


class SubjectKind(str, Enum):
    PERSON = "person"
    HOUSEHOLD = "household"


@dataclass(frozen=True, slots=True)
class Subject:
    kind: SubjectKind
    id: str

    def __post_init__(self):
        if not isinstance(self.kind, SubjectKind):
            raise ValueError("expected a subject kind")
        identifier(self.id)


@dataclass(frozen=True, slots=True)
class Owner:
    person_id: str
    share: Decimal | None = None

    def __post_init__(self):
        identifier(self.person_id)
        if self.share is not None:
            decimal_value(self.share)
            if not 0 < self.share <= 1:
                raise ValueError("ownership shares must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class Ownership:
    owners: tuple[Owner, ...]

    def __post_init__(self):
        owners = distinct_records(self.owners, Owner, key=lambda owner: owner.person_id)
        shares = [owner.share for owner in owners if owner.share is not None]
        if not owners or (shares and (len(shares) != len(owners) or decimal_sum(shares) != 1)):
            raise ValueError("ownership requires people and shares must be absent or sum to one")
        object.__setattr__(self, "owners", owners)

    def person_ids(self) -> frozenset[str]:
        return frozenset(owner.person_id for owner in self.owners)

    def share_within(self, person_ids: frozenset[str]) -> Decimal | None:
        """Return the covered legal share, or unknown for a partial group without shares."""
        covered = self.person_ids() & person_ids
        if not covered:
            return Decimal(0)
        if len(covered) == len(self.owners):
            return Decimal(1)
        if self.owners[0].share is None:
            return None
        return decimal_sum(
            owner.share for owner in self.owners
            if owner.person_id in covered and owner.share is not None
        )


class AccountKind(str, Enum):
    DEPOSIT = "deposit"
    BROKERAGE = "brokerage"
    EMPLOYER_RETIREMENT = "employer_retirement"
    INDIVIDUAL_RETIREMENT = "individual_retirement"
    HEALTH_SAVINGS = "health_savings"
    EDUCATION_SAVINGS = "education_savings"
    OTHER = "other"


class TaxTreatment(str, Enum):
    TAXABLE = "taxable"
    TAX_DEFERRED = "tax_deferred"
    ROTH = "roth"
    PURPOSE_SPECIFIC = "purpose_specific"
    OTHER = "other"


class Access(str, Enum):
    UNRESTRICTED = "unrestricted"
    CONDITIONAL = "conditional"
    LOCKED = "locked"


class AssetClass(str, Enum):
    CASH = "cash"
    FIXED_INCOME = "fixed_income"
    EQUITY = "equity"
    REAL_ASSETS = "real_assets"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Holding:
    id: str
    asset_class: AssetClass
    security_id: str | None = None
    value: Money | None = None
    weight: Decimal | None = None

    def __post_init__(self):
        identifier(self.id)
        if not isinstance(self.asset_class, AssetClass):
            raise ValueError("expected an asset class")
        if self.security_id is not None:
            identifier(self.security_id)
        if (self.value is None) == (self.weight is None):
            raise ValueError("a holding needs exactly one of value or weight")
        if self.value is not None:
            if not isinstance(self.value, Money) or self.value.amount < 0:
                raise ValueError("holding value must be nonnegative money")
        if self.weight is not None:
            decimal_value(self.weight, minimum=0)
            if self.weight > 1:
                raise ValueError("holding weight must be in [0, 1]")


def _position(id, name, kind, kind_type, ownership, valuation, source):
    identifier(id)
    identifier(name)
    if not isinstance(kind, kind_type):
        raise ValueError(f"expected a {kind_type.__name__}")
    if not isinstance(ownership, Ownership) or not isinstance(valuation, Valuation):
        raise ValueError("financial positions require ownership and a valuation")
    validate_source(source, SourceKind.USER_FACT)


@dataclass(frozen=True, slots=True)
class Account:
    id: str
    name: str
    kind: AccountKind
    ownership: Ownership
    valuation: Valuation
    tax_treatment: TaxTreatment | None = None
    access: Access | None = None
    access_note: str | None = None
    holdings: tuple[Holding, ...] = ()
    beneficiary_ids: tuple[str, ...] = ()
    source: Source | None = None

    def __post_init__(self):
        _position(self.id, self.name, self.kind, AccountKind, self.ownership,
                  self.valuation, self.source)
        if self.tax_treatment is not None and not isinstance(self.tax_treatment, TaxTreatment):
            raise ValueError("expected an account tax treatment")
        if self.access is not None and not isinstance(self.access, Access):
            raise ValueError("expected an account access classification")
        if self.access_note is not None and not isinstance(self.access_note, str):
            raise ValueError("expected an account access note")
        holdings = distinct_records(self.holdings, Holding)
        values = [holding.value for holding in holdings if holding.value is not None]
        if values:
            if len(values) != len(holdings) or self.valuation.amount is None:
                raise ValueError("valued holdings require a known account value and a single basis")
            for value in values:
                value.require_currency(self.valuation.currency)
            if decimal_sum(value.amount for value in values) > self.valuation.amount:
                raise ValueError("holding values exceed account value")
        elif decimal_sum(holding.weight for holding in holdings if holding.weight is not None) > 1:
            raise ValueError("holding weights exceed one")
        object.__setattr__(self, "holdings", holdings)
        object.__setattr__(self, "beneficiary_ids", distinct_ids(self.beneficiary_ids))


class AssetKind(str, Enum):
    REAL_ESTATE = "real_estate"
    VEHICLE = "vehicle"
    BUSINESS_INTEREST = "business_interest"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Asset:
    id: str
    name: str
    kind: AssetKind
    ownership: Ownership
    valuation: Valuation
    source: Source | None = None

    def __post_init__(self):
        _position(self.id, self.name, self.kind, AssetKind, self.ownership,
                  self.valuation, self.source)


class LiabilityKind(str, Enum):
    MORTGAGE = "mortgage"
    INSTALLMENT_LOAN = "installment_loan"
    REVOLVING = "revolving"
    OTHER = "other"


class RateKind(str, Enum):
    FIXED = "fixed"
    VARIABLE = "variable"


@dataclass(frozen=True, slots=True)
class DebtTerms:
    rate_kind: RateKind | None = None
    annual_rate: Decimal | None = None
    maturity_on: date | None = None

    def __post_init__(self):
        if self.rate_kind is not None and not isinstance(self.rate_kind, RateKind):
            raise ValueError("expected a debt rate kind")
        if self.annual_rate is not None:
            decimal_value(self.annual_rate, minimum=0)
        if self.maturity_on is not None:
            calendar_date(self.maturity_on)


@dataclass(frozen=True, slots=True)
class Liability:
    id: str
    name: str
    kind: LiabilityKind
    responsibility: Ownership
    balance: Valuation
    terms: DebtTerms | None = None
    source: Source | None = None

    def __post_init__(self):
        _position(self.id, self.name, self.kind, LiabilityKind, self.responsibility,
                  self.balance, self.source)
        if self.terms is not None and not isinstance(self.terms, DebtTerms):
            raise ValueError("expected debt terms")


@dataclass(frozen=True, slots=True)
class FinancialProfile:
    revision: Revision
    currency: str
    people: tuple[Person, ...] = ()
    household: Household | None = None
    accounts: tuple[Account, ...] = ()
    assets: tuple[Asset, ...] = ()
    liabilities: tuple[Liability, ...] = ()
    source: Source | None = None

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("expected a profile revision")
        currency_code(self.currency)
        validate_source(self.source, SourceKind.USER_FACT)
        for field, record_type in (
            ("people", Person), ("accounts", Account), ("assets", Asset),
            ("liabilities", Liability),
        ):
            object.__setattr__(self, field, distinct_records(getattr(self, field), record_type))

        people = {person.id for person in self.people}
        if self.household is not None and (
            not isinstance(self.household, Household)
            or not people.issuperset(self.household.member_ids)
        ):
            raise ValueError("household contains unknown people")

        seen = set()
        for record in (*self.accounts, *self.assets, *self.liabilities):
            if record.id in seen:
                raise ValueError("financial entity identifiers must be unique across kinds")
            seen.add(record.id)
            if isinstance(record, Liability):
                parties, value = record.responsibility, record.balance
            else:
                parties, value = record.ownership, record.valuation
            if not people.issuperset(parties.person_ids()):
                raise ValueError(f"{record.id} references an unknown owner or obligor")
            if isinstance(record, Account) and not people.issuperset(record.beneficiary_ids):
                raise ValueError(f"{record.id} references an unknown beneficiary")
            if self.currency != value.currency:
                raise ValueError(f"{record.id} valuation requires profile currency {self.currency}")

    def people_in(self, subject: Subject) -> frozenset[str]:
        if subject.kind is SubjectKind.PERSON and any(p.id == subject.id for p in self.people):
            return frozenset((subject.id,))
        if (subject.kind is SubjectKind.HOUSEHOLD and self.household is not None
                and subject.id == self.household.id):
            return frozenset(self.household.member_ids)
        raise ValueError(f"unknown analysis subject {subject.id}")

    def positions_for(self, subject: Subject) -> tuple[Account | Asset | Liability, ...]:
        """Return participating records once, with their full legal relationships."""
        people = self.people_in(subject)
        return (
            *(record for record in (*self.accounts, *self.assets)
              if people & record.ownership.person_ids()),
            *(record for record in self.liabilities if people & record.responsibility.person_ids()),
        )
