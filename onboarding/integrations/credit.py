import hashlib

from .base import BaseIntegrationClient, IntegrationResponse, deterministic_bucket, magic_override


def _seed_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()

# Most normal demo applicants receive a strong bureau result. REVIEW and FAIL
# values still provide deterministic manual-review and rejection scenarios.
BUCKETS = ("strong",) * 9 + ("moderate",)

OVERRIDE_MAP = {
    "FAIL": "insufficient",
    "REVIEW": "weak",
}

SCORE_RANGE = {
    "strong": (700, 900),
    "moderate": (600, 699),
    "weak": (500, 599),
    "insufficient": (300, 499),
}

DEPENDANT_MONTHLY_ALLOWANCE = 350
MAX_DEBT_TO_INCOME_RATIO = 0.40
MIN_STABLE_EMPLOYMENT_MONTHS = 6


class CreditBureauClient(BaseIntegrationClient):
    """Mocks a personal (UC/ASNEF/BIK-style) or business credit bureau plus
    a simple affordability calculation."""

    check_type = "credit"

    def _call(self, payload: dict) -> IntegrationResponse:
        # Production bureau calls would need a properly protected legal
        # identifier. This sample uses a keyed subject reference so it can
        # keep source identifiers out of persisted answers.
        subject_id = str(
            payload.get("credit_subject_reference")
            or payload.get("national_id")
            or payload.get("business_id")
            or ""
        )
        seed = f"credit:{subject_id}"

        override = magic_override(subject_id)
        outcome = OVERRIDE_MAP.get(override) or deterministic_bucket(seed, BUCKETS)

        lo, hi = SCORE_RANGE[outcome]
        digest = int(_seed_hash(seed), 16)
        score = lo + (digest % (hi - lo + 1))

        income = float(payload.get("monthly_income") or 0)
        housing_cost = float(payload.get("monthly_housing_cost") or 0)
        other_living_costs = float(payload.get("monthly_other_living_costs") or 0)
        debt_payments = float(payload.get("monthly_debt_payments") or 0)
        dependants = int(float(payload.get("dependants") or 0))
        employment_months = int(float(payload.get("employment_months") or 0))
        employment_status = payload.get("employment_status")
        turnover = float(payload.get("annual_turnover") or 0)
        requested = float(payload.get("requested_amount") or 0)

        if income:
            dependant_allowance = dependants * DEPENDANT_MONTHLY_ALLOWANCE
            disposable_income = round(
                income - housing_cost - other_living_costs - debt_payments - dependant_allowance,
                2,
            )
        elif turnover:
            disposable_income = round(turnover / 12 * 0.3, 2)  # rough monthly cash-flow proxy
            dependant_allowance = 0.0
        else:
            disposable_income = 0.0
            dependant_allowance = 0.0

        debt_flags = outcome in {"weak", "insufficient"}
        affordability_ok = disposable_income > 0 and requested <= disposable_income * 36
        debt_to_income_ratio = round(debt_payments / income, 3) if income else None
        employment_stable = (
            employment_status in {"employed", "self_employed", "retired"}
            and employment_months >= MIN_STABLE_EMPLOYMENT_MONTHS
        ) if income else None

        reasons = []
        if outcome == "insufficient":
            reasons.append("Bureau score below minimum threshold")
        if debt_flags:
            reasons.append("Existing debt flags on file")
        if not affordability_ok:
            reasons.append("Requested amount exceeds affordability estimate")
        if debt_to_income_ratio is not None and debt_to_income_ratio > MAX_DEBT_TO_INCOME_RATIO:
            reasons.append("Existing monthly debt payments are high relative to income")
        if employment_stable is False:
            reasons.append("Employment history requires manual assessment")
        if not reasons:
            reasons.append("Score and affordability within normal range")

        return IntegrationResponse(
            outcome=outcome,
            details={
                "score": score,
                "debt_flags": debt_flags,
                "disposable_income": disposable_income,
                "affordability_ok": affordability_ok,
                "dependant_allowance": dependant_allowance,
                "debt_to_income_ratio": debt_to_income_ratio,
                "employment_stable": employment_stable,
                "decision_reason": "; ".join(reasons),
            },
        )
