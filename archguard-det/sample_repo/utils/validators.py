"""Deterministic input validation helpers."""

import re

EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_email(email: str) -> bool:
    """Return True if email matches standard RFC-like format."""
    if not isinstance(email, str):
        return False
    return bool(EMAIL_PATTERN.match(email.strip()))


def validate_positive_int(value: object) -> bool:
    """Return True if value is an integer strictly greater than zero."""
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value > 0


def validate_price(price: object) -> bool:
    """Return True if price is a non-negative numeric value."""
    if isinstance(price, bool) or not isinstance(price, (int, float)):
        return False
    return float(price) >= 0.0


def sanitize_text(value: str, max_length: int = 200) -> str:
    """Strip surrounding whitespace and clamp string length."""
    if not isinstance(value, str):
        return ""
    cleaned = " ".join(value.strip().split())
    return cleaned[:max_length]
