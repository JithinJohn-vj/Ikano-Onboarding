import time

from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override

BUCKETS = ("iban_verified",) * 7 + ("name_mismatch",) * 2 + ("unreachable",) * 1

OVERRIDE_MAP = {
    "FAIL": "name_mismatch",
    "REVIEW": "name_mismatch",
    "TIMEOUT": "unreachable",
}

MAX_ATTEMPTS = 3
# Deliberately short so tests/demo stay fast; a real client would use
# proper timeouts and backoff.
RETRY_SLEEP_SECONDS = 0.01


class BankAccountClient(BaseIntegrationClient):
    """Mocks IBAN/account-holder verification. Simulates a transient
    'unreachable' provider with a couple of retries before giving up --
    demonstrates graceful fallback to manual review rather than a hard
    crash when a downstream service is flaky."""

    check_type = "bank"

    def _call(self, payload: dict) -> IntegrationResponse:
        iban = str(payload.get("iban", ""))
        legal_name = str(payload.get("legal_name", ""))
        seed = f"bank:{iban}:{legal_name}"

        override = magic_override(iban, legal_name)
        force_persistent_timeout = override == "TIMEOUT"
        base_outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)

        attempts = 1
        outcome = base_outcome
        if base_outcome == "unreachable":
            # Simulate transient provider flakiness: retry with backoff.
            # Unless a persistent timeout was forced, the provider recovers
            # by the final attempt -- a realistic "retry then succeed" path.
            while attempts < MAX_ATTEMPTS:
                time.sleep(RETRY_SLEEP_SECONDS)
                attempts += 1
            outcome = "unreachable" if force_persistent_timeout else "iban_verified"

        return IntegrationResponse(
            outcome=outcome,
            details={"attempts_before_result": attempts},
            attempt_count=attempts,
        )
