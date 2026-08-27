from onboarding.models import AuditEvent


def log_event(application, event_type: str, message: str, metadata: dict | None = None):
    """Every call site is responsible for making sure `message` and
    `metadata` are already free of raw sensitive values -- this function
    does not attempt to re-derive that, it just writes what it's given.
    Callers should pass masked/aggregate data only (see redaction.py and
    the integration clients' `details` dicts, which never carry raw PII)."""
    return AuditEvent.objects.create(
        application=application,
        event_type=event_type,
        message=message,
        metadata=metadata or {},
    )
