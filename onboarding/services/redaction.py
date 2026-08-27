"""
Sensitive fields (national IDs, IBANs, etc.) are declared as such in the
flow schema (`Field.sensitive = True`). We never persist the raw value in
`StepAnswer.data` or in any `IntegrationResult.details` / `AuditEvent`
row -- only a masked representation, kept just precise enough to be useful
for support/debugging (e.g. "confirm the customer typed the ID we think
they did") without being a raw PII store.

The raw value is still passed in-memory to the relevant mock integration
call for that one request/response cycle, matching how a real KYC/KYB
provider call would work -- it is simply never written to disk unmasked.
"""

import hashlib
import hmac

from django.conf import settings


def mask_value(value: str) -> str:
    value = str(value)
    if len(value) <= 4:
        return "*" * len(value)
    visible = value[-4:]
    return "*" * (len(value) - 4) + visible


def redact_step_data(fields, submitted: dict) -> dict:
    """Given the Field definitions for a step and the raw submitted dict,
    return a copy safe to persist: sensitive fields are masked."""
    redacted = dict(submitted)
    for f in fields:
        if f.sensitive and f.name in redacted and redacted[f.name]:
            redacted[f.name] = mask_value(redacted[f.name])
    return redacted


def subject_reference(value: str) -> str:
    """Return a stable, keyed reference for a sensitive integration subject.

    A later mock credit check needs a stable subject key, but retaining a
    national or business identifier just for that purpose would undermine the
    redaction boundary. An HMAC is deterministic for this installation and
    cannot be reversed without the application secret.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256
    ).hexdigest()
