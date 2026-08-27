import hashlib
import secrets
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Application(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        SUBMITTED = "submitted", "Submitted"
        MANUAL_REVIEW = "manual_review", "Manual review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        ABANDONED = "abandoned", "Abandoned"
        EXPIRED = "expired", "Expired"

    class AccountType(models.TextChoices):
        INDIVIDUAL = "individual", "Private individual"
        BUSINESS = "business", "Business"

    class Country(models.TextChoices):
        SWEDEN = "SE", "Sweden"
        SPAIN = "ES", "Spain"
        POLAND = "PL", "Poland"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    country = models.CharField(max_length=2, choices=Country.choices)
    account_type = models.CharField(max_length=16, choices=AccountType.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.IN_PROGRESS)
    current_step_key = models.CharField(max_length=64, blank=True)

    # Resume token is stored hashed; only the raw token (given to the user
    # once, in the magic link) can be used to look the application up.
    resume_token_hash = models.CharField(max_length=64, blank=True, db_index=True)
    resume_token_expires_at = models.DateTimeField(null=True, blank=True)

    decision_outcome = models.CharField(max_length=16, blank=True)
    decision_reasons = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.id} ({self.country}/{self.account_type}, {self.status})"

    # -- resume token helpers ------------------------------------------------

    @staticmethod
    def _hash_token(raw_token: str) -> str:
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

    def issue_resume_token(self) -> str:
        """Generate a fresh raw resume token, store only its hash, and
        return the raw token so the caller can hand it to the user via a
        magic link. The raw value is never persisted."""
        raw_token = secrets.token_urlsafe(32)
        self.resume_token_hash = self._hash_token(raw_token)
        ttl_hours = getattr(settings, "RESUME_TOKEN_TTL_HOURS", 72)
        self.resume_token_expires_at = timezone.now() + timezone.timedelta(hours=ttl_hours)
        self.save(update_fields=["resume_token_hash", "resume_token_expires_at"])
        return raw_token

    def resume_token_is_valid(self, raw_token: str) -> bool:
        if not self.resume_token_hash or not raw_token:
            return False
        if self.resume_token_expires_at and timezone.now() > self.resume_token_expires_at:
            return False
        return secrets.compare_digest(self._hash_token(raw_token), self.resume_token_hash)

    def is_terminal(self) -> bool:
        return self.status in {
            self.Status.SUBMITTED,
            self.Status.MANUAL_REVIEW,
            self.Status.APPROVED,
            self.Status.REJECTED,
            self.Status.ABANDONED,
            self.Status.EXPIRED,
        }

    def mark_touched(self):
        """Called on every meaningful interaction; used to decide, on
        access, whether a long-idle in-progress application should flip to
        'abandoned' instead of running a background job."""
        if self.status != self.Status.IN_PROGRESS:
            return
        idle_hours = getattr(settings, "ABANDONED_AFTER_HOURS", 24)
        if timezone.now() - self.updated_at > timezone.timedelta(hours=idle_hours):
            self.status = self.Status.ABANDONED
            self.save(update_fields=["status"])


class StepAnswer(models.Model):
    """One row per completed step. `data` holds the field values that were
    submitted, with any field marked `sensitive=True` in the flow schema
    replaced by a masked representation before it ever reaches the DB."""

    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="answers")
    step_key = models.CharField(max_length=64)
    data = models.JSONField(default=dict)
    completed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("application", "step_key")
        ordering = ["completed_at"]

    def __str__(self):
        return f"{self.application_id} / {self.step_key}"


class IntegrationResult(models.Model):
    """Result of a mocked external check. `details` is restricted to
    decision-relevant, non-sensitive fields (never raw national IDs, IBANs,
    etc.) -- see redaction rules applied in the integration clients."""

    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="integration_results")
    request_id = models.UUIDField(default=uuid.uuid4, editable=False)
    check_type = models.CharField(max_length=32)  # identity | address | registry | authority | sanctions | credit | bank
    step_key = models.CharField(max_length=64)
    outcome = models.CharField(max_length=32)
    details = models.JSONField(default=dict)
    latency_ms = models.IntegerField(default=0)
    attempt_count = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.check_type}:{self.outcome} ({self.application_id})"


class AuditEvent(models.Model):
    """Append-only audit trail. `message` and `metadata` are sanitized at
    the point of creation (see services/audit_service.py) -- this table
    must never contain raw sensitive answers."""

    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="audit_events")
    event_id = models.UUIDField(default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=48)
    message = models.CharField(max_length=255)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.created_at:%Y-%m-%d %H:%M:%S}] {self.event_type}: {self.message}"
