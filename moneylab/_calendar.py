"""Internal calendar operations shared by monthly models."""

from datetime import date


def month_boundary(start: date, months: int) -> date:
    years, month = divmod(start.month - 1 + months, 12)
    return date(start.year + years, month + 1, 1)
