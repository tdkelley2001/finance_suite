"""Shared value conventions for the canonical domain."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, localcontext
from enum import Enum
import re


def identifier(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("identifiers must be nonempty strings without outer whitespace")


def currency_code(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("currency must be a three-letter uppercase code")


def calendar_date(value: date) -> None:
    if type(value) is not date:
        raise ValueError("expected a calendar date")


def decimal_value(value: Decimal, *, minimum: Decimal | int | None = None) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("expected a finite Decimal")
    if value.as_tuple().exponent < -8 or (value and value.adjusted() >= 18):
        raise ValueError("Decimal values support 18 integer and 8 fractional places")
    if minimum is not None and value < minimum:
        raise ValueError(f"value must be at least {minimum}")


def decimal_sum(values: Iterable[Decimal]) -> Decimal:
    # Leave room above the supported value precision for exact validation totals.
    with localcontext(Context(prec=40)):
        return sum(values, start=Decimal(0))


def integer(value: int, *, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"expected an integer of at least {minimum}")


def distinct_records(values, record_type, *, key=lambda record: record.id):
    records = tuple(values)
    if any(not isinstance(record, record_type) for record in records):
        raise ValueError(f"expected {record_type.__name__} records")
    keys = [key(record) for record in records]
    if len(set(keys)) != len(keys):
        raise ValueError(f"duplicate {record_type.__name__} identifier")
    return tuple(sorted(records, key=key))


def distinct_ids(values) -> tuple[str, ...]:
    if isinstance(values, str):
        raise ValueError("expected a collection of identifiers")
    ids = tuple(values)
    for value in ids:
        identifier(value)
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate identifier")
    return tuple(sorted(ids))


class SourceKind(str, Enum):
    USER_FACT = "user_fact"
    USER_PLAN = "user_plan"
    EXTERNAL_DATA = "external_data"
    PRESET = "preset"
    RESEARCH_DEFAULT = "research_default"
    SCENARIO_OVERRIDE = "scenario_override"
    LOCAL_OVERRIDE = "local_override"


@dataclass(frozen=True, slots=True)
class Revision:
    id: str
    version: str

    def __post_init__(self):
        identifier(self.id)
        identifier(self.version)


@dataclass(frozen=True, slots=True)
class Source:
    kind: SourceKind
    reference: Revision | None = None

    def __post_init__(self):
        if not isinstance(self.kind, SourceKind):
            raise ValueError("expected a source kind")
        if self.reference is not None and not isinstance(self.reference, Revision):
            raise ValueError("expected a versioned source reference")


def validate_source(source: Source | None, kind: SourceKind) -> None:
    if source is not None and (
        not isinstance(source, Source) or source.kind not in {kind, SourceKind.EXTERNAL_DATA}
    ):
        raise ValueError(f"source must be {kind.value} or external data")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        decimal_value(self.amount)
        currency_code(self.currency)

    def require_currency(self, currency: str) -> None:
        if self.currency != currency:
            raise ValueError(f"expected {currency}, got {self.currency}")


@dataclass(frozen=True, slots=True)
class Valuation:
    currency: str
    amount: Decimal | None = None
    as_of: date | None = None

    def __post_init__(self):
        currency_code(self.currency)
        if self.as_of is not None:
            calendar_date(self.as_of)
        if self.amount is not None:
            decimal_value(self.amount, minimum=0)
            if self.as_of is None:
                raise ValueError("a known valuation requires a date")
