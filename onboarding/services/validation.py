import re
import math
from datetime import date, datetime

from onboarding.flows.schema import Field, FieldType, Step

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StepValidationError(Exception):
    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("Step validation failed")


def _validate_field(f: Field, raw_value):
    """Returns (cleaned_value, error_message_or_None)."""
    if f.type == FieldType.CHECKBOX:
        checked = raw_value in ("on", "true", "True", "1", True)
        if f.required and not checked:
            return None, "This must be confirmed to continue."
        return checked, None

    value = (raw_value or "").strip() if isinstance(raw_value, str) else raw_value

    if f.required and (value is None or value == ""):
        return value, "This field is required."

    if value in (None, "") and not f.required:
        return value, None

    if isinstance(value, str):
        if f.min_length is not None and len(value) < f.min_length:
            return value, f"Enter at least {f.min_length} characters."
        if f.max_length is not None and len(value) > f.max_length:
            return value, f"Enter no more than {f.max_length} characters."

    if f.type == FieldType.EMAIL and not EMAIL_RE.match(value):
        return value, "Enter a valid email address."

    if f.type == FieldType.NUMBER:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return value, "Enter a valid number."
        if not math.isfinite(num):
            return value, "Enter a finite number."
        if f.integer_only and not num.is_integer():
            return value, "Enter a whole number."
        if f.min_value is not None and num < f.min_value:
            return num, f"Must be at least {f.min_value}."
        if f.max_value is not None and num > f.max_value:
            return num, f"Must be at most {f.max_value}."
        return num, None

    if f.type == FieldType.DATE:
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return value, "Enter a valid date (YYYY-MM-DD)."
        if parsed > date.today():
            return value, "Date cannot be in the future."
        return value, None

    if f.type == FieldType.SELECT:
        valid_values = {c[0] for c in f.choices}
        if value not in valid_values:
            return value, "Choose one of the listed options."
        return value, None

    if f.pattern and not re.match(f.pattern, value):
        return value, f.pattern_message

    return value, None


def validate_step(step: Step, raw_data: dict):
    """Validate submitted form data against a step's field definitions.
    Returns a cleaned dict on success or raises StepValidationError with a
    field-name-keyed error dict."""
    cleaned = {}
    errors = {}
    for f in step.fields:
        value, error = _validate_field(f, raw_data.get(f.name))
        cleaned[f.name] = value
        if error:
            errors[f.name] = error
    if errors:
        raise StepValidationError(errors)
    return cleaned
