"""Compatibility exports; new code should use ``moneylab.engine``."""

from moneylab.engine.calculations import (
    CashFlowSnapshot,
    amortization_schedule,
    cash_flow_snapshot,
    cash_required,
    compound_value,
    constrained_payment_limit,
    fixed_payment,
)

__all__ = [
    "CashFlowSnapshot", "amortization_schedule", "cash_flow_snapshot",
    "cash_required", "compound_value", "constrained_payment_limit", "fixed_payment",
]

