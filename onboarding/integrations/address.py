from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override

BUCKETS = ("verified",) * 8 + ("unverifiable",) * 1 + ("manual_review",) * 1

OVERRIDE_MAP = {
    "FAIL": "unverifiable",
    "REVIEW": "manual_review",
}


class AddressLookupClient(BaseIntegrationClient):
    """Mocks a national address/postcode lookup service. Treated as
    informational in decisioning (it nudges towards manual review but is
    never a hard fail on its own -- addresses get typo'd a lot)."""

    check_type = "address"

    def _call(self, payload: dict) -> IntegrationResponse:
        seed = f"address:{payload.get('postal_code', '')}:{payload.get('city', '')}:{payload.get('street_address', '')}"
        override = magic_override(payload.get("postal_code"), payload.get("city"))
        outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)
        return IntegrationResponse(outcome=outcome, details={"match_type": "exact" if outcome == "verified" else "partial"})
