"""Versioned research coverage and explicit custom exposures."""

from dataclasses import dataclass
from enum import Enum

from moneylab.domain.values import Revision, distinct_records, identifier


class ExposureCategory(str, Enum):
    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    CASH = "cash"
    REAL_ESTATE = "real_estate"
    COMMODITY = "commodity"
    OTHER = "other"


class ResearchPriority(str, Enum):
    CORE = "core"
    EXTENDED = "extended"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class ExposureDefinition:
    id: str
    label: str
    category: ExposureCategory
    priority: ResearchPriority

    def __post_init__(self):
        identifier(self.id)
        identifier(self.label)
        if not isinstance(self.category, ExposureCategory) or not isinstance(self.priority, ResearchPriority):
            raise ValueError("exposure needs an explicit category and research priority")
        if self.id.startswith("custom.") != (self.priority is ResearchPriority.CUSTOM):
            raise ValueError("custom exposure identifiers use the custom. namespace")


@dataclass(frozen=True, slots=True)
class ExposureTaxonomy:
    revision: Revision
    definitions: tuple[ExposureDefinition, ...]

    def __post_init__(self):
        if not isinstance(self.revision, Revision):
            raise ValueError("taxonomy requires a revision")
        object.__setattr__(self, "definitions", distinct_records(self.definitions, ExposureDefinition))

    def require(self, exposure_id: str) -> ExposureDefinition:
        for definition in self.definitions:
            if definition.id == exposure_id:
                return definition
        raise ValueError(f"unknown economic exposure {exposure_id}")


def _definitions(category, priority, rows):
    return tuple(ExposureDefinition(key, label, category, priority) for key, label in rows)


DEFAULT_TAXONOMY = ExposureTaxonomy(Revision("moneylab-investment-exposures", "1.0.0"), (
    *_definitions(ExposureCategory.EQUITY, ResearchPriority.CORE, (
        ("us-equity-broad", "US broad-market equities"),
        ("developed-international-equity", "Developed international equities"),
        ("emerging-market-equity", "Emerging-market equities"),
    )),
    *_definitions(ExposureCategory.FIXED_INCOME, ResearchPriority.CORE, (
        ("us-treasury-short", "Short-term US Treasuries"),
        ("us-treasury-intermediate", "Intermediate-term US Treasuries"),
        ("us-corporate-investment-grade", "Investment-grade corporate bonds"),
        ("us-bond-aggregate", "Broad US aggregate bonds"),
    )),
    ExposureDefinition("cash", "Cash and cash equivalents", ExposureCategory.CASH, ResearchPriority.CORE),
    *_definitions(ExposureCategory.EQUITY, ResearchPriority.EXTENDED, (
        ("us-equity-large-cap", "US large-cap equities"),
        ("us-equity-mid-cap", "US mid-cap equities"),
        ("us-equity-small-cap", "US small-cap equities"),
        ("us-equity-growth", "US growth equities"),
        ("us-equity-value", "US value equities"),
    )),
    *_definitions(ExposureCategory.FIXED_INCOME, ResearchPriority.EXTENDED, (
        ("us-treasury-long", "Long-term US Treasuries"),
        ("inflation-protected-bonds", "Inflation-protected bonds"),
        ("us-corporate-high-yield", "High-yield corporate bonds"),
        ("international-bonds", "International bonds"),
    )),
    ExposureDefinition("public-real-estate", "Public real estate securities",
                       ExposureCategory.REAL_ESTATE, ResearchPriority.EXTENDED),
    ExposureDefinition("commodities", "Commodities", ExposureCategory.COMMODITY, ResearchPriority.EXTENDED),
))
