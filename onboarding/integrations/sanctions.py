from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override

BUCKETS = ("no_hit",) * 8 + ("possible_hit",) * 1 + ("confirmed_hit",) * 1

OVERRIDE_MAP = {
    "FAIL": "confirmed_hit",
    "REVIEW": "possible_hit",
    "CONFIRMED_HIT": "confirmed_hit",
}


class SanctionsScreeningClient(BaseIntegrationClient):
    """Mocks a PEP/sanctions list screening provider. Can be called with a
    single name or a comma-separated list of names (for UBO screening) --
    if any name in the list would hit, the whole check reflects the worst
    result."""

    check_type = "sanctions"
    _SEVERITY = {"no_hit": 0, "possible_hit": 1, "confirmed_hit": 2}

    def _call(self, payload: dict) -> IntegrationResponse:
        raw_names = payload.get("ubo_names") or payload.get("full_name") or ""
        names = [n.strip() for n in str(raw_names).split(",") if n.strip()] or ["unknown"]

        worst_outcome = "no_hit"
        screened = []
        for name in names:
            seed = f"sanctions:{name.lower()}"
            override = magic_override(name)
            outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)
            screened.append({"screened": True, "result": outcome})
            if self._SEVERITY[outcome] > self._SEVERITY[worst_outcome]:
                worst_outcome = outcome

        return IntegrationResponse(
            outcome=worst_outcome,
            details={"names_screened": len(names), "worst_result": worst_outcome},
        )
