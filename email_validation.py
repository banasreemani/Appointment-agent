"""Deterministic patient email validation."""

from email_validator import EmailNotValidError, validate_email


def normalize_email_address(value: str) -> str | None:
    """Return a normalized syntactically valid email address, or ``None``."""
    candidate = value.strip()
    if not candidate:
        return None

    try:
        result = validate_email(candidate, check_deliverability=False)
    except EmailNotValidError:
        return None
    return result.normalized
