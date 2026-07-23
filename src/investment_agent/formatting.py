from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def format_money(value: Decimal | None, currency: str = "USD") -> str:
    if value is None:
        return "unavailable"
    rounded = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if rounded < 0 else ""
    amount = abs(rounded)
    symbol = "$" if currency == "USD" else f"{currency} "
    return f"{sign}{symbol}{amount:,.2f}"


def format_signed_money(value: Decimal | None, currency: str = "USD") -> str:
    if value is None:
        return "unavailable"
    prefix = "+" if value > 0 else ""
    return f"{prefix}{format_money(value, currency)}"


def format_percent(value: Decimal | None, *, signed: bool = False) -> str:
    if value is None:
        return "unavailable"
    rounded = value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    prefix = "+" if signed and rounded > 0 else ""
    return f"{prefix}{rounded}%"


def title_enum(value: str) -> str:
    return value.replace("_", " ").title()
