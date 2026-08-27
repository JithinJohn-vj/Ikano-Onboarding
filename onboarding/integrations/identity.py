import hashlib

from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override

# The normal demo path should be easy to complete successfully. Explicit
# REVIEW and FAIL values still exercise the exceptional paths deterministically.
BUCKETS = (
    "verified", "verified", "verified", "verified", "verified",
    "verified", "verified", "verified", "verified",
    "manual_review",
)

OVERRIDE_MAP = {
    "FAIL": "document_mismatch",
    "REVIEW": "manual_review",
}


class IdentityCheckClient(BaseIntegrationClient):
    """Mocks a BankID/Cl@ve/eID-style identity verification provider."""

    check_type = "identity"

    def _call(self, payload: dict) -> IntegrationResponse:
        national_id = str(payload.get("national_id") or payload.get("rep_national_id") or "")
        full_name = str(payload.get("full_name") or payload.get("rep_full_name") or "")
        seed = f"identity:{national_id}:{full_name}"

        override = magic_override(national_id, full_name)
        outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)

        # A stable "confidence" score derived from the same seed, purely
        # for realism in the audit/decision detail -- not itself sensitive.
        confidence = 0.55 + (int(hashlib.sha256(seed.encode()).hexdigest(), 16) % 45) / 100

        return IntegrationResponse(
            outcome=outcome,
            details={
                "identity_confidence": round(confidence, 2) if outcome == "verified" else round(confidence * 0.6, 2),
                "provider_reference": f"IDV-{deterministic_bucket(seed, tuple(f'{i:04d}' for i in range(1000)))}",
            },
        )
