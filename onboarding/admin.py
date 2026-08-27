from django.contrib import admin

from .models import Application, AuditEvent, IntegrationResult, StepAnswer


class StepAnswerInline(admin.TabularInline):
    model = StepAnswer
    extra = 0
    readonly_fields = ("step_key", "data", "completed_at")
    can_delete = False


class IntegrationResultInline(admin.TabularInline):
    model = IntegrationResult
    extra = 0
    readonly_fields = ("check_type", "step_key", "outcome", "details", "latency_ms", "attempt_count", "created_at")
    can_delete = False


class AuditEventInline(admin.TabularInline):
    model = AuditEvent
    extra = 0
    readonly_fields = ("event_type", "message", "metadata", "created_at")
    can_delete = False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "country", "account_type", "status", "current_step_key", "created_at", "decision_outcome")
    list_filter = ("country", "account_type", "status")
    readonly_fields = (
        "id", "resume_token_hash", "resume_token_expires_at", "created_at", "updated_at",
        "submitted_at", "decided_at",
    )
    inlines = [StepAnswerInline, IntegrationResultInline, AuditEventInline]


@admin.register(IntegrationResult)
class IntegrationResultAdmin(admin.ModelAdmin):
    list_display = ("application", "check_type", "outcome", "attempt_count", "latency_ms", "created_at")
    list_filter = ("check_type", "outcome")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("application", "event_type", "message", "created_at")
    list_filter = ("event_type",)
