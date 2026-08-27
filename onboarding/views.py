import hashlib
import logging

from django.contrib import messages
from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from onboarding.flows.country_config import COUNTRIES
from onboarding.flows.definitions import get_flow
from onboarding.models import Application
from onboarding.services import application_service
from onboarding.services.application_service import ApplicationFlowError
from onboarding.services.validation import StepValidationError

SESSION_ACCESS_KEY = "app_access"
logger = logging.getLogger(__name__)


def csrf_failure(request, reason=""):
    """Keep CSRF protection active and record the actionable failure reason."""
    logger.warning("CSRF rejection for %s: %s", request.path, reason)
    return HttpResponse(
        "<h1>Forbidden (403)</h1><p>CSRF verification failed. "
        "Check the development-server terminal for the reason.</p>",
        status=403,
    )


def _grant_access(request, application_id, *, rotate_session=False):
    if rotate_session:
        request.session.cycle_key()
    granted = set(request.session.get(SESSION_ACCESS_KEY, []))
    granted.add(str(application_id))
    request.session[SESSION_ACCESS_KEY] = list(granted)


def _has_access(request, application_id) -> bool:
    return str(application_id) in request.session.get(SESSION_ACCESS_KEY, [])


def _resume_attempt_allowed(request) -> bool:
    """Apply a bounded per-source limit to magic-link token attempts."""
    source_address = request.META.get("REMOTE_ADDR", "unknown")
    key = "resume-attempts:" + hashlib.sha256(source_address.encode()).hexdigest()
    if cache.add(key, 1, timeout=settings.RESUME_ATTEMPT_WINDOW_SECONDS):
        return True
    try:
        attempts = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=settings.RESUME_ATTEMPT_WINDOW_SECONDS)
        return True
    return attempts <= settings.RESUME_MAX_ATTEMPTS


class _AccessDenied(Exception):
    def __init__(self, application):
        self.application = application


def _load_with_access(request, application_id):
    """Fetch an application, enforcing that this browser session was
    granted access when the application was created or resumed. This is a
    deliberately simple substitute for real authentication -- see README
    assumptions. Applications are looked up by UUID, never a guessable
    sequential ID."""
    application = get_object_or_404(Application, id=application_id)
    if not _has_access(request, application_id):
        messages.warning(request, "Use your resume link to continue this application.")
        raise _AccessDenied(application)
    application.mark_touched()
    return application


def _build_field_rows(step, raw_values=None, errors=None, existing_data=None):
    raw_values = raw_values or {}
    errors = errors or {}
    existing_data = existing_data or {}
    rows = []
    for f in step.fields:
        if f.name in raw_values:
            value = raw_values.get(f.name)
        elif f.name in existing_data and not f.sensitive:
            value = existing_data.get(f.name)
        else:
            value = ""
        rows.append({"field": f, "value": value, "error": errors.get(f.name)})
    return rows


def _progress(flow, current_key):
    keys = flow.step_keys()
    try:
        idx = keys.index(current_key)
    except ValueError:
        idx = len(keys) - 1
    return {"current": idx + 1, "total": len(keys), "percent": round((idx) / max(len(keys) - 1, 1) * 100)}


# --------------------------------------------------------------------------
# Start / country + account type selection
# --------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
@ensure_csrf_cookie
def start(request):
    countries = COUNTRIES.values()
    account_types = Application.AccountType.choices

    if request.method == "POST":
        country = request.POST.get("country")
        account_type = request.POST.get("account_type")
        if country not in COUNTRIES or account_type not in dict(account_types):
            messages.error(request, "Please choose a country and account type.")
            return render(request, "onboarding/start.html", {"countries": countries, "account_types": account_types})

        application, raw_token = application_service.start_application(country, account_type)
        _grant_access(request, application.id)
        resume_url = request.build_absolute_uri(reverse("resume_magic_link", args=[raw_token]))
        request.session["last_resume_url"] = resume_url
        messages.info(request, f"Save this link to resume later if you get interrupted: {resume_url}")
        flow = get_flow(country, account_type)
        return redirect("step", application_id=application.id, step_key=flow.first_step().key)

    return render(request, "onboarding/start.html", {"countries": countries, "account_types": account_types})


# --------------------------------------------------------------------------
# Step form
# --------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def step(request, application_id, step_key):
    try:
        application = _load_with_access(request, application_id)
    except _AccessDenied:
        return redirect("resume_entry")

    if application.is_terminal():
        return redirect("result", application_id=application.id)

    flow = get_flow(application.country, application.account_type)
    step_def = flow.get_step(step_key)
    if step_def is None:
        raise Http404("Unknown step")

    if step_def.kind == "review":
        return redirect("review", application_id=application.id)

    if step_key != application.current_step_key:
        # No going back to a completed step, and no skipping ahead --
        # always bounce to the application's actual current step.
        return redirect("step", application_id=application.id, step_key=application.current_step_key)

    existing = application.answers.filter(step_key=step_key).first()

    if request.method == "POST":
        try:
            application_service.submit_step(application, step_key, request.POST)
        except StepValidationError as e:
            rows = _build_field_rows(step_def, raw_values=request.POST, errors=e.errors)
            messages.error(request, "Please fix the highlighted fields.")
            return render(
                request,
                "onboarding/step_form.html",
                {"application": application, "step": step_def, "rows": rows, "progress": _progress(flow, step_key)},
            )
        except ApplicationFlowError as e:
            messages.error(request, str(e))
            return redirect("step", application_id=application.id, step_key=application.current_step_key)

        application.refresh_from_db()
        next_step_def = flow.get_step(application.current_step_key)
        if next_step_def and next_step_def.kind == "review":
            return redirect("review", application_id=application.id)
        return redirect("step", application_id=application.id, step_key=application.current_step_key)

    rows = _build_field_rows(step_def, existing_data=existing.data if existing else {})
    return render(
        request,
        "onboarding/step_form.html",
        {"application": application, "step": step_def, "rows": rows, "progress": _progress(flow, step_key)},
    )


# --------------------------------------------------------------------------
# Review & submit
# --------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def review(request, application_id):
    try:
        application = _load_with_access(request, application_id)
    except _AccessDenied:
        return redirect("resume_entry")

    if application.is_terminal():
        return redirect("result", application_id=application.id)

    flow = get_flow(application.country, application.account_type)
    if application.current_step_key != flow.steps[-1].key:
        messages.warning(request, "Complete the remaining steps before reviewing your application.")
        return redirect("step", application_id=application.id, step_key=application.current_step_key)

    if request.method == "POST":
        if request.POST.get("terms_accepted") != "on":
            messages.error(request, "You must accept the terms to submit the application.")
        else:
            try:
                application_service.finalize_application(application)
            except ApplicationFlowError as e:
                messages.error(request, str(e))
                return redirect("review", application_id=application.id)
            return redirect("result", application_id=application.id)

    answers = []
    for ans in application.answers.all():
        step_def = flow.get_step(ans.step_key)
        answers.append({"step_title": step_def.title if step_def else ans.step_key, "data": ans.data})

    integration_results = application.integration_results.all()

    return render(
        request,
        "onboarding/review.html",
        {
            "application": application,
            "answers": answers,
            "integration_results": integration_results,
            "progress": _progress(flow, "review"),
        },
    )


# --------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------

def result(request, application_id):
    try:
        application = _load_with_access(request, application_id)
    except _AccessDenied:
        return redirect("resume_entry")

    return render(request, "onboarding/result.html", {"application": application})


# --------------------------------------------------------------------------
# Audit trail (would sit behind staff auth in a real deployment -- see
# README assumptions; kept open here so it's easy to inspect in the demo)
# --------------------------------------------------------------------------

def audit_trail(request, application_id):
    try:
        application = _load_with_access(request, application_id)
    except _AccessDenied:
        return redirect("resume_entry")

    events = application.audit_events.all()
    return render(request, "onboarding/audit.html", {"application": application, "events": events})


# --------------------------------------------------------------------------
# Resume via magic link / pasted token
# --------------------------------------------------------------------------

@require_http_methods(["GET", "POST"])
def resume_entry(request):
    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        return redirect("resume_magic_link", token=token)
    return render(request, "onboarding/resume.html")


def resume_magic_link(request, token):
    if not _resume_attempt_allowed(request):
        return HttpResponse(
            "Too many resume attempts. Please wait before trying again.", status=429
        )
    try:
        application = application_service.resume_application(token)
    except ApplicationFlowError as e:
        messages.error(request, str(e))
        return redirect("resume_entry")

    _grant_access(request, application.id, rotate_session=True)

    if application.is_terminal():
        return redirect("result", application_id=application.id)
    return redirect("step", application_id=application.id, step_key=application.current_step_key)
