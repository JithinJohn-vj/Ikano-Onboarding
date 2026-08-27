from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override

BUCKETS = (
    "active_company", "active_company", "active_company", "active_company",
    "active_company", "active_company",
    "unknown_representative", "unknown_representative",
    "missing_ubo",
    "dissolved",
)

OVERRIDE_MAP = {
    "FAIL": "dissolved",
    "REVIEW": "unknown_representative",
}


class RegistryClient(BaseIntegrationClient):
    """Mocks a company registry lookup (Bolagsverket / Registro Mercantil /
    CEIDG-KRS style)."""

    check_type = "registry"

    def _call(self, payload: dict) -> IntegrationResponse:
        business_id = str(payload.get("business_id", ""))
        legal_name = str(payload.get("legal_name", ""))
        seed = f"registry:{business_id}:{legal_name}"

        override = magic_override(business_id, legal_name)
        outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)

        return IntegrationResponse(
            outcome=outcome,
            details={
                "registry_status": outcome,
                "directors_on_file": outcome in {"active_company", "missing_ubo"},
            },
        )
