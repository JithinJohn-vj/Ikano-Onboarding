from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override


BUCKETS = ("authorised",) * 8 + ("unknown_representative",) + ("no_authority",)
OVERRIDE_MAP = {"FAIL": "no_authority", "REVIEW": "unknown_representative"}


class SignatoryAuthorityClient(BaseIntegrationClient):
    """Mocks a company-register check that a representative may sign."""

    check_type = "authority"

    def _call(self, payload: dict) -> IntegrationResponse:
        name = str(payload.get("rep_full_name", ""))
        national_id = str(payload.get("rep_national_id", ""))
        declared_rights = payload.get("signatory_rights")

        if declared_rights != "yes":
            outcome = "no_authority"
        else:
            override = magic_override(name, national_id)
            outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(
                f"authority:{name}:{national_id}", BUCKETS
            )

        return IntegrationResponse(
            outcome=outcome,
            details={"authority_confirmed": outcome == "authorised"},
        )
