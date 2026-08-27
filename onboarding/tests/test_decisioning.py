from dataclasses import dataclass

from django.test import SimpleTestCase

from onboarding.decisioning.engine import APPROVED, MANUAL_REVIEW, REJECT, decide


@dataclass
class FakeResult:
    check_type: str
    outcome: str
    details: dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}


class DecisioningTests(SimpleTestCase):
    def test_all_clean_checks_approve(self):
        results = [
            FakeResult("identity", "verified"),
            FakeResult("address", "verified"),
            FakeResult("sanctions", "no_hit"),
            FakeResult("credit", "strong", {"affordability_ok": True}),
        ]
        decision = decide(results)
        self.assertEqual(decision.outcome, APPROVED)

    def test_confirmed_sanctions_hit_rejects_regardless_of_other_checks(self):
        results = [
            FakeResult("identity", "verified"),
            FakeResult("credit", "strong", {"affordability_ok": True}),
            FakeResult("sanctions", "confirmed_hit"),
        ]
        decision = decide(results)
        self.assertEqual(decision.outcome, REJECT)
        self.assertIn("Confirmed sanctions/PEP match", decision.reasons)

    def test_missing_signatory_authority_rejects_business_application(self):
        decision = decide([FakeResult("authority", "no_authority")])
        self.assertEqual(decision.outcome, "rejected")

    def test_manual_review_outcome_does_not_escalate_to_reject(self):
        results = [
            FakeResult("identity", "verified"),
            FakeResult("credit", "moderate", {"affordability_ok": True}),
        ]
        decision = decide(results)
        self.assertEqual(decision.outcome, MANUAL_REVIEW)

    def test_reject_beats_manual_review_when_both_present(self):
        results = [
            FakeResult("credit", "moderate", {"affordability_ok": True}),
            FakeResult("identity", "expired_id"),
        ]
        decision = decide(results)
        self.assertEqual(decision.outcome, REJECT)

    def test_unaffordable_amount_forces_manual_review_even_with_strong_score(self):
        results = [
            FakeResult("credit", "strong", {"affordability_ok": False}),
        ]
        decision = decide(results)
        self.assertEqual(decision.outcome, MANUAL_REVIEW)

    def test_short_employment_history_forces_manual_review(self):
        decision = decide([
            FakeResult("credit", "strong", {"affordability_ok": True, "employment_stable": False}),
        ])
        self.assertEqual(decision.outcome, MANUAL_REVIEW)
        self.assertIn("Employment history requires manual assessment", decision.reasons)

    def test_no_results_still_returns_a_decision_with_a_reason(self):
        decision = decide([])
        self.assertEqual(decision.outcome, APPROVED)
        self.assertTrue(decision.reasons)

    def test_unknown_check_type_or_outcome_is_ignored_not_crashed(self):
        results = [FakeResult("some_future_check", "weird_outcome")]
        decision = decide(results)
        self.assertEqual(decision.outcome, APPROVED)
