"""
Deterministic decisioning: takes every IntegrationResult recorded for an
application and produces a final outcome.

Design: outcomes have a strict priority order (reject beats manual review
beats approve). Each check contributes zero or more reasons at a given
severity; we take the worst severity seen and surface all of its reasons.
This keeps the logic a simple, testable reduction rather than nested
conditionals per country/account type -- the same decisioning function runs
for every flow.
"""
from __future__ import annotations

from dataclasses import dataclass, field

REJECT = "rejected"
MANUAL_REVIEW = "manual_review"
APPROVED = "approved"

_SEVERITY_ORDER = {APPROVED: 0, MANUAL_REVIEW: 1, REJECT: 2}

# check_type -> outcome -> (severity, reason)
RULES = {
    "identity": {
        "verified": None,
        "manual_review": (MANUAL_REVIEW, "Identity check flagged for manual review"),
        "document_mismatch": (REJECT, "Identity document did not match applicant details"),
        "expired_id": (REJECT, "Identity document is expired"),
    },
    "address": {
        "verified": None,
        "unverifiable": (MANUAL_REVIEW, "Address could not be automatically verified"),
        "manual_review": (MANUAL_REVIEW, "Address check flagged for manual review"),
    },
    "registry": {
        "active_company": None,
        "unknown_representative": (MANUAL_REVIEW, "Representative not found on company registry"),
        "missing_ubo": (MANUAL_REVIEW, "Beneficial owner information missing from registry"),
        "dissolved": (REJECT, "Company registry shows the business as dissolved"),
    },
    "authority": {
        "authorised": None,
        "unknown_representative": (MANUAL_REVIEW, "Representative authority requires manual verification"),
        "no_authority": (REJECT, "Representative does not have authority to sign for the business"),
    },
    "sanctions": {
        "no_hit": None,
        "possible_hit": (MANUAL_REVIEW, "Possible sanctions/PEP match requires manual screening"),
        "confirmed_hit": (REJECT, "Confirmed sanctions/PEP match"),
    },
    "credit": {
        "strong": None,
        "moderate": (MANUAL_REVIEW, "Credit bureau result requires manual affordability review"),
        "weak": (MANUAL_REVIEW, "Weak credit bureau result requires manual review"),
        "insufficient": (REJECT, "Credit bureau score below minimum threshold"),
    },
    "bank": {
        "iban_verified": None,
        "name_mismatch": (MANUAL_REVIEW, "Settlement account name does not match applicant/business"),
        "unreachable": (MANUAL_REVIEW, "Bank could not be reached to verify the settlement account"),
    },
}


@dataclass
class Decision:
    outcome: str
    reasons: list = field(default_factory=list)


def decide(integration_results) -> Decision:
    """`integration_results` is an iterable of objects with `.check_type`
    and `.outcome` attributes (IntegrationResult instances, or anything
    duck-typed the same way for tests)."""
    worst = APPROVED
    reasons: list[str] = []

    for result in integration_results:
        rule_set = RULES.get(result.check_type, {})
        rule = rule_set.get(result.outcome)
        if rule is not None:
            severity, reason = rule
            reasons.append(reason)
            if _SEVERITY_ORDER[severity] > _SEVERITY_ORDER[worst]:
                worst = severity

        # Affordability is a cross-cutting flag on the credit check's
        # details rather than its own outcome bucket -- handled separately
        # so a "strong" score with an unaffordable requested amount still
        # lands in manual review instead of auto-approving.
        if result.check_type == "credit":
            details = result.details or {}
            if details.get("affordability_ok") is False:
                reasons.append("Requested amount exceeds affordability estimate")
                if _SEVERITY_ORDER[MANUAL_REVIEW] > _SEVERITY_ORDER[worst]:
                    worst = MANUAL_REVIEW
            debt_to_income_ratio = details.get("debt_to_income_ratio")
            if debt_to_income_ratio is not None and debt_to_income_ratio > 0.40:
                reasons.append("Existing monthly debt payments are high relative to income")
                if _SEVERITY_ORDER[MANUAL_REVIEW] > _SEVERITY_ORDER[worst]:
                    worst = MANUAL_REVIEW
            if details.get("employment_stable") is False:
                reasons.append("Employment history requires manual assessment")
                if _SEVERITY_ORDER[MANUAL_REVIEW] > _SEVERITY_ORDER[worst]:
                    worst = MANUAL_REVIEW

    if not reasons:
        reasons.append("All checks passed automatically")

    return Decision(outcome=worst, reasons=reasons)
