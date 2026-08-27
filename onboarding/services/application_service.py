"""
The orchestration layer that ties everything together:

  flow definition (what steps exist)
  + validation (is this step's submission valid)
  + persistence (StepAnswer, redacted)
  + integration layer (mock external checks)
  + decisioning (final outcome)
  + audit trail (what happened, when)

Views should be thin and call into this module rather than embedding this
logic directly, so the flow can be driven the same way from the web UI,
from a management command, or from tests.
"""
from __future__ import annotations

import uuid

from django.utils import timezone

from onboarding.decisioning.engine import decide
from onboarding.flows.definitions import get_flow
from onboarding.integrations.registry import get_client
from onboarding.models import Application, IntegrationResult, StepAnswer

from . import audit_service
from .redaction import redact_step_data, subject_reference
from .validation import StepValidationError, validate_step


class ApplicationFlowError(Exception):
    pass


def start_application(country: str, account_type: str) -> tuple[Application, str]:
    """Creates a new Application, positions it at the first step of its
    flow, issues a resume token, and returns (application, raw_token)."""
    flow = get_flow(country, account_type)  # raises ValueError for bad combos
    application = Application.objects.create(
        country=country,
        account_type=account_type,
        current_step_key=flow.first_step().key,
        status=Application.Status.IN_PROGRESS,
    )
    raw_token = application.issue_resume_token()
    audit_service.log_event(
        application,
        "application_created",
        f"Application started for {country}/{account_type}",
        {"flow_steps": flow.step_keys()},
    )
    return application, raw_token


def get_answers_dict(application: Application) -> dict:
    """Merge every completed step's safe-to-persist answers into one dict.

    Sensitive identifiers remain masked. When needed by a later mock credit
    check, the flow uses ``credit_subject_reference``: a keyed,
    non-reversible reference created at the collection boundary.
    """
    merged = {}
    for answer in application.answers.all():
        merged.update(answer.data)
    return merged


def _run_integration(application: Application, step, step_key: str, live_field_values: dict):
    """Runs the mock integration declared on a step, using live (unmasked)
    field values for the call, but only ever storing decision-relevant,
    non-sensitive `details` in the DB."""
    spec = step.integration
    client = get_client(spec.check_type)
    request_id = str(uuid.uuid4())

    payload = {name: live_field_values.get(name) for name in spec.input_fields}
    response = client.call(payload, request_id)

    result = IntegrationResult.objects.create(
        application=application,
        request_id=request_id,
        check_type=spec.check_type,
        step_key=step_key,
        outcome=response.outcome,
        details=response.details,
        latency_ms=response.latency_ms,
        attempt_count=response.attempt_count,
    )
    audit_service.log_event(
        application,
        "integration_result",
        f"{spec.check_type} check on step '{step_key}' returned '{response.outcome}'",
        {"check_type": spec.check_type, "outcome": response.outcome, "request_id": request_id},
    )
    return result


def submit_step(application: Application, step_key: str, raw_form_data: dict):
    """Validate + persist a step submission, run any declared integration,
    and advance the application to the next step. Returns the (possibly
    updated) application. Raises StepValidationError on bad input."""
    if application.is_terminal():
        raise ApplicationFlowError("This application has already reached a final state.")

    flow = get_flow(application.country, application.account_type)
    step = flow.get_step(step_key)
    if step is None or step_key != application.current_step_key:
        raise ApplicationFlowError("This step is not the application's current step.")

    cleaned = validate_step(step, raw_form_data)  # raises StepValidationError

    redacted = redact_step_data(step.fields, cleaned)
    # Credit checks happen after identifier collection. Preserve a stable
    # correlation key, not the raw identifier, for that later call.
    for identifier_field in ("national_id", "business_id"):
        if identifier_field in cleaned:
            redacted["credit_subject_reference"] = subject_reference(cleaned[identifier_field])
    StepAnswer.objects.update_or_create(
        application=application, step_key=step_key, defaults={"data": redacted}
    )
    audit_service.log_event(
        application, "step_completed", f"Step '{step.title}' completed", {"step_key": step_key}
    )

    if step.integration:
        # Values may span earlier steps. Sensitive identifiers are represented
        # by their keyed credit reference rather than their stored mask.
        live_values = get_answers_dict(application)
        live_values.update(cleaned)
        _run_integration(application, step, step_key, live_values)

    next_step = flow.next_step(step_key)
    application.current_step_key = next_step.key if next_step else step_key
    application.updated_at = timezone.now()
    application.save(update_fields=["current_step_key", "updated_at"])
    return application


def finalize_application(application: Application):
    """Called from the review step: run decisioning over every recorded
    integration result and move the application to a terminal state."""
    if application.is_terminal():
        raise ApplicationFlowError("This application has already reached a final state.")

    flow = get_flow(application.country, application.account_type)
    review_step = flow.steps[-1]
    if review_step.kind != "review" or application.current_step_key != review_step.key:
        raise ApplicationFlowError("Complete every required step before submitting this application.")

    completed_checks = {
        (result.step_key, result.check_type) for result in application.integration_results.all()
    }
    missing_checks = [
        step.key
        for step in flow.steps
        if step.integration and (step.key, step.integration.check_type) not in completed_checks
    ]
    if missing_checks:
        raise ApplicationFlowError("Required verification checks are incomplete.")

    results = list(application.integration_results.all())
    decision = decide(results)

    if decision.outcome == "approved":
        status = Application.Status.APPROVED
    elif decision.outcome == "manual_review":
        status = Application.Status.MANUAL_REVIEW
    else:
        status = Application.Status.REJECTED

    application.status = status
    application.decision_outcome = decision.outcome
    application.decision_reasons = decision.reasons
    application.submitted_at = timezone.now()
    application.decided_at = timezone.now()
    application.save(
        update_fields=["status", "decision_outcome", "decision_reasons", "submitted_at", "decided_at"]
    )

    audit_service.log_event(
        application,
        "decision_made",
        f"Final decision: {decision.outcome}",
        {"outcome": decision.outcome, "reasons": decision.reasons},
    )
    return application


def resume_application(raw_token: str) -> Application:
    """Looks up an application by (hashed) resume token. Raises
    ApplicationFlowError if the token is invalid/expired/unknown."""
    token_hash = Application._hash_token(raw_token)
    try:
        application = Application.objects.get(resume_token_hash=token_hash)
    except Application.DoesNotExist:
        raise ApplicationFlowError("This resume link is invalid.")

    if not application.resume_token_is_valid(raw_token):
        if application.status == Application.Status.IN_PROGRESS:
            application.status = Application.Status.EXPIRED
            application.save(update_fields=["status"])
        raise ApplicationFlowError("This resume link has expired.")

    application.mark_touched()
    audit_service.log_event(application, "resumed", "Application resumed via magic link", {})
    return application
