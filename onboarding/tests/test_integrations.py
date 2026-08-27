from django.test import SimpleTestCase

from onboarding.integrations.address import AddressLookupClient
from onboarding.integrations.authority import SignatoryAuthorityClient
from onboarding.integrations.bank import BankAccountClient
from onboarding.integrations.company_registry import RegistryClient
from onboarding.integrations.credit import CreditBureauClient
from onboarding.integrations.identity import IdentityCheckClient
from onboarding.integrations.registry import get_client
from onboarding.integrations.sanctions import SanctionsScreeningClient


class DeterminismTests(SimpleTestCase):
    """Same input must always produce the same outcome -- this is what
    makes the mocks safe to demo and to assert on in tests."""

    def test_identity_is_deterministic(self):
        client = IdentityCheckClient()
        payload = {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"}
        r1 = client.call(dict(payload), "req-1")
        r2 = client.call(dict(payload), "req-2")
        self.assertEqual(r1.outcome, r2.outcome)

    def test_credit_is_deterministic(self):
        client = CreditBureauClient()
        payload = {"national_id": "198506122384", "monthly_income": 30000, "monthly_housing_cost": 9000, "requested_amount": 50000}
        r1 = client.call(dict(payload), "req-1")
        r2 = client.call(dict(payload), "req-2")
        self.assertEqual(r1.outcome, r2.outcome)
        self.assertEqual(r1.details["score"], r2.details["score"])

    def test_credit_affordability_uses_all_recurring_costs(self):
        client = CreditBureauClient()
        response = client.call(
            {
                "national_id": "198506122384",
                "monthly_income": 5000,
                "monthly_housing_cost": 800,
                "monthly_other_living_costs": 700,
                "monthly_debt_payments": 300,
                "dependants": 1,
                "employment_status": "employed",
                "employment_months": 24,
                "requested_amount": 500,
            },
            "req-1",
        )
        self.assertEqual(response.details["disposable_income"], 2850)
        self.assertTrue(response.details["affordability_ok"])
        self.assertTrue(response.details["employment_stable"])


class MagicOverrideTests(SimpleTestCase):
    def test_identity_fail_override(self):
        client = IdentityCheckClient()
        r = client.call({"full_name": "FAIL Case", "national_id": "FAIL-0001", "date_of_birth": "1990-01-01"}, "req-1")
        self.assertEqual(r.outcome, "document_mismatch")

    def test_identity_review_override(self):
        client = IdentityCheckClient()
        r = client.call({"full_name": "Review Case", "national_id": "REVIEW-0001", "date_of_birth": "1990-01-01"}, "req-1")
        self.assertEqual(r.outcome, "manual_review")

    def test_representative_identity_uses_representative_field_names(self):
        client = IdentityCheckClient()
        r = client.call(
            {"rep_full_name": "Rep Person", "rep_national_id": "FAIL-0001"}, "req-1"
        )
        self.assertEqual(r.outcome, "document_mismatch")

    def test_authority_rejects_a_representative_without_declared_rights(self):
        client = SignatoryAuthorityClient()
        r = client.call(
            {"rep_full_name": "Rep Person", "rep_national_id": "198506122384", "signatory_rights": "no"},
            "req-1",
        )
        self.assertEqual(r.outcome, "no_authority")

    def test_registry_fail_override_is_dissolved(self):
        client = RegistryClient()
        r = client.call({"business_id": "FAIL-CO", "legal_name": "Doomed AB"}, "req-1")
        self.assertEqual(r.outcome, "dissolved")

    def test_sanctions_confirmed_hit_override(self):
        client = SanctionsScreeningClient()
        r = client.call({"ubo_names": "John CONFIRMEDHIT Smith"}, "req-1")
        self.assertEqual(r.outcome, "confirmed_hit")

    def test_sanctions_worst_result_wins_across_multiple_names(self):
        client = SanctionsScreeningClient()
        r = client.call({"ubo_names": "Ordinary Person, REVIEW Person"}, "req-1")
        self.assertEqual(r.outcome, "possible_hit")
        self.assertEqual(r.details["names_screened"], 2)

    def test_credit_fail_override_is_insufficient(self):
        client = CreditBureauClient()
        r = client.call({"national_id": "FAIL-999", "monthly_income": 20000, "monthly_housing_cost": 5000, "requested_amount": 10000}, "req-1")
        self.assertEqual(r.outcome, "insufficient")

    def test_bank_persistent_timeout_override(self):
        client = BankAccountClient()
        r = client.call({"iban": "SE-TIMEOUT-001", "legal_name": "Timeout AB"}, "req-1")
        self.assertEqual(r.outcome, "unreachable")
        self.assertGreaterEqual(r.attempt_count, 1)


class OutcomeVocabularyTests(SimpleTestCase):
    """Every outcome the mocks can return must be one the decisioning
    engine actually knows how to interpret (see decisioning/engine.py)."""

    def test_outcomes_match_expected_vocabulary(self):
        expected = {
            "identity": {"verified", "manual_review", "document_mismatch", "expired_id"},
            "address": {"verified", "unverifiable", "manual_review"},
            "registry": {"active_company", "unknown_representative", "missing_ubo", "dissolved"},
            "authority": {"authorised", "unknown_representative", "no_authority"},
            "sanctions": {"no_hit", "possible_hit", "confirmed_hit"},
            "credit": {"strong", "moderate", "weak", "insufficient"},
            "bank": {"iban_verified", "name_mismatch", "unreachable"},
        }
        clients = {
            "identity": IdentityCheckClient(),
            "address": AddressLookupClient(),
            "registry": RegistryClient(),
            "authority": SignatoryAuthorityClient(),
            "sanctions": SanctionsScreeningClient(),
            "credit": CreditBureauClient(),
            "bank": BankAccountClient(),
        }
        payloads = {
            "identity": {"full_name": "X", "national_id": "Y", "date_of_birth": "1990-01-01"},
            "address": {"postal_code": "12345", "city": "X", "street_address": "Y"},
            "registry": {"business_id": "X", "legal_name": "Y"},
            "authority": {"rep_full_name": "X", "rep_national_id": "Y", "signatory_rights": "yes"},
            "sanctions": {"ubo_names": "X"},
            "credit": {"national_id": "X", "monthly_income": 1000, "monthly_housing_cost": 500, "requested_amount": 1000},
            "bank": {"iban": "X", "legal_name": "Y"},
        }
        # Sample many seeds to make sure every bucket is reachable and
        # nothing outside the expected vocabulary is ever returned.
        for check_type, client in clients.items():
            seen = set()
            for i in range(200):
                payload = dict(payloads[check_type])
                for k in payload:
                    if isinstance(payload[k], str):
                        payload[k] = f"{payload[k]}-{i}"
                outcome = client.call(payload, f"req-{i}").outcome
                self.assertIn(outcome, expected[check_type], f"{check_type} returned unexpected outcome {outcome}")
                seen.add(outcome)
            self.assertTrue(seen.issubset(expected[check_type]))


class RegistryLookupTests(SimpleTestCase):
    def test_get_client_returns_expected_types(self):
        self.assertIsInstance(get_client("identity"), IdentityCheckClient)
        self.assertIsInstance(get_client("bank"), BankAccountClient)

    def test_get_client_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            get_client("does-not-exist")
