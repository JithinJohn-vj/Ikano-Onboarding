"""
Data-driven flow schema.

The onboarding journey for any (country, account_type) pair is expressed as
a `Flow` made of an ordered list of `Step`s. Steps that collect data list
their `Field`s declaratively (type + validation rules). Steps that need an
external check declare an `integration` spec instead of raw fields.

Because everything is data, adding a new country or a new step means adding
configuration in `definitions.py` -- not touching the view/engine code, and
not adding another branch to an if/else tree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class FieldType(str, Enum):
    TEXT = "text"
    EMAIL = "email"
    DATE = "date"
    NUMBER = "number"
    SELECT = "select"
    CHECKBOX = "checkbox"
    TEXTAREA = "textarea"


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    type: FieldType = FieldType.TEXT
    required: bool = True
    help_text: str = ""
    choices: tuple = ()  # for SELECT: tuple of (value, label)
    pattern: Optional[str] = None  # regex, applied server-side
    pattern_message: str = "This value doesn't look right."
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    integer_only: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    sensitive: bool = False  # if True, value is masked before it is persisted


@dataclass(frozen=True)
class IntegrationSpec:
    """Declares that, once this step's form is submitted, a mock external
    check should run using the listed field(s) as input."""
    check_type: str  # matches a key in integrations.registry.INTEGRATIONS
    input_fields: tuple  # field names from this step (or earlier steps) to pass in
    # Which outcomes from this integration should immediately halt the
    # journey (hard stop) vs. just get recorded for the final decision.
    hard_fail_outcomes: tuple = ()


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    description: str = ""
    fields: tuple = ()  # tuple[Field, ...]
    integration: Optional[IntegrationSpec] = None
    kind: str = "form"  # "form" | "review"


@dataclass(frozen=True)
class Flow:
    country: str
    account_type: str
    steps: tuple  # tuple[Step, ...]

    def step_keys(self) -> list:
        return [s.key for s in self.steps]

    def get_step(self, key: str) -> Optional[Step]:
        for s in self.steps:
            if s.key == key:
                return s
        return None

    def first_step(self) -> Step:
        return self.steps[0]

    def next_step(self, current_key: str) -> Optional[Step]:
        keys = self.step_keys()
        try:
            idx = keys.index(current_key)
        except ValueError:
            return None
        if idx + 1 < len(keys):
            return self.steps[idx + 1]
        return None

    def is_last(self, key: str) -> bool:
        return self.step_keys()[-1] == key
