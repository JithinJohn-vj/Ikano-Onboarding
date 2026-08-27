from django.test import TestCase
from django.utils import timezone

from onboarding.flows.definitions import get_flow
from onboarding.models import Application, AuditEvent, IntegrationResult, StepAnswer
from onboarding.services import application_service
from onboarding.services.application_service import ApplicationFlowError
from onboarding.services.validation import StepValidationError


class StartApplicationTests(TestCase):
    def test_start_application_creates_record_at_first_step(self):
        application, raw_token = application_service.start_application("SE", "individual")
        flow = get_flow("SE", "individual")
        self.assertEqual(application.status, Application.Status.IN_PROGRESS)
        self.assertEqual(application.current_step_key, flow.first_step().key)
        self.assertTrue(raw_token)
        self.assertTrue(application.resume_token_hash)
        # raw token must never be persisted anywhere
        self.assertNotEqual(application.resume_token_hash, raw_token)

    def test_start_application_logs_audit_event(self):
        application, _ = application_service.start_application("PL", "business")
        events = list(application.audit_events.all())
        self.assertEqual(events[0].event_type, "application_created")


class SubmitStepTests(TestCase):
    def setUp(self):
        self.application, self.token = application_service.start_application("SE", "individual")

    def test_valid_submission_advances_to_next_step(self):
        flow = get_flow("SE", "individual")
        application_service.submit_step(
            self.application,
            "identity",
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        self.application.refresh_from_db()
        expected_next = flow.next_step("identity").key
        self.assertEqual(self.application.current_step_key, expected_next)

    def test_invalid_submission_does_not_advance_and_raises(self):
        with self.assertRaises(StepValidationError):
            application_service.submit_step(self.application, "identity", {"full_name": "", "national_id": "", "date_of_birth": ""})
        self.application.refresh_from_db()
        self.assertEqual(self.application.current_step_key, "identity")

    def test_sensitive_field_is_masked_in_stored_answer(self):
        application_service.submit_step(
            self.application,
            "identity",
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        answer = StepAnswer.objects.get(application=self.application, step_key="identity")
        self.assertNotEqual(answer.data["national_id"], "198506122384")
        self.assertTrue(answer.data["national_id"].endswith("2384"))

    def test_step_with_integration_records_integration_result(self):
        application_service.submit_step(
            self.application,
            "identity",
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        results = IntegrationResult.objects.filter(application=self.application, check_type="identity")
        self.assertEqual(results.count(), 1)

    def test_wrong_step_key_raises_flow_error(self):
        with self.assertRaises(ApplicationFlowError):
            application_service.submit_step(self.application, "financials", {})

    def test_cannot_submit_step_on_terminal_application(self):
        self.application.status = Application.Status.REJECTED
        self.application.save()
        with self.assertRaises(ApplicationFlowError):
            application_service.submit_step(self.application, "identity", {})

    def test_cross_step_field_reuse_for_integration_input(self):
        # national_id collected at 'identity' should still be available for
        # the 'credit_check' step's integration input later in the flow.
        application_service.submit_step(
            self.application,
            "identity",
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        application_service.submit_step(
            self.application,
            "contact",
            {
                "email": "anna@example.com", "phone": "+46701234567", "street_address": "Storgatan One",
                "postal_code": "11122", "city": "Stockholm", "region": "Stockholm County",
            },
        )
        application_service.submit_step(
            self.application,
            "consent",
            {"privacy_consent": "on", "pep_declaration": "no"},
        )
        application_service.submit_step(
            self.application,
            "financials",
            {"employment_status": "employed", "monthly_income": "35000", "monthly_housing_cost": "9000", "dependants": "1", "monthly_other_living_costs": "5000", "monthly_debt_payments": "0", "employment_months": "24"},
        )
        application_service.submit_step(
            self.application, "credit_check", {"requested_amount": "20000"}
        )
        merged = application_service.get_answers_dict(self.application)
        self.assertTrue(merged["national_id"].endswith("2384"))
        self.assertIn("credit_subject_reference", merged)
        self.assertNotIn("198506122384", merged["credit_subject_reference"])


class FinalizeApplicationTests(TestCase):
    def setUp(self):
        self.application, self.token = application_service.start_application("SE", "individual")

    def _complete_happy_path(self):
        application_service.submit_step(
            self.application, "identity",
            {"full_name": "Clean Applicant", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        application_service.submit_step(
            self.application, "contact",
            {"email": "clean@example.com", "phone": "+46700000000", "street_address": "Storgatan One",
             "postal_code": "11122", "city": "Stockholm", "region": "Stockholm"},
        )
        application_service.submit_step(
            self.application, "consent",
            {"privacy_consent": "on", "pep_declaration": "no"},
        )
        application_service.submit_step(
            self.application, "financials",
            {"employment_status": "employed", "monthly_income": "40000", "monthly_housing_cost": "8000", "dependants": "1", "monthly_other_living_costs": "5000", "monthly_debt_payments": "0", "employment_months": "24"},
        )
        application_service.submit_step(self.application, "credit_check", {"requested_amount": "10000"})
        self.application.refresh_from_db()

    def test_finalize_sets_terminal_status_and_decision(self):
        self._complete_happy_path()
        application_service.finalize_application(self.application)
        self.application.refresh_from_db()
        self.assertIn(self.application.status, [
            Application.Status.APPROVED, Application.Status.MANUAL_REVIEW, Application.Status.REJECTED,
        ])
        self.assertTrue(self.application.decision_outcome)
        self.assertTrue(self.application.decision_reasons)
        self.assertIsNotNone(self.application.decided_at)

    def test_finalize_logs_decision_audit_event(self):
        self._complete_happy_path()
        application_service.finalize_application(self.application)
        self.assertTrue(
            AuditEvent.objects.filter(application=self.application, event_type="decision_made").exists()
        )

    def test_cannot_finalize_twice(self):
        self._complete_happy_path()
        application_service.finalize_application(self.application)
        self.application.refresh_from_db()
        with self.assertRaises(ApplicationFlowError):
            application_service.finalize_application(self.application)

    def test_cannot_finalize_before_all_steps_are_complete(self):
        with self.assertRaisesRegex(ApplicationFlowError, "Complete every required step"):
            application_service.finalize_application(self.application)

    def test_forced_sanctions_hit_rejects_business_application(self):
        application, _ = application_service.start_application("SE", "business")
        application_service.submit_step(
            application, "company",
            {"legal_name": "Acme AB", "business_id": "556677-8899", "legal_form": "llc"},
        )
        application_service.submit_step(
            application, "representative",
            {"rep_full_name": "Rep Person", "rep_national_id": "198506122384", "rep_role": "CEO", "signatory_rights": "yes"},
        )
        application_service.submit_step(application, "authority_check", {})
        application_service.submit_step(
            application, "ubo", {"ubo_names": "CONFIRMEDHIT Person", "ubo_total_ownership_pct": "100"},
        )
        application_service.submit_step(
            application, "consent",
            {"privacy_consent": "on", "pep_declaration": "no"},
        )
        application_service.submit_step(
            application, "business_profile",
            {"sector": "Retail", "annual_turnover": "1000000", "expected_usage": "Working capital"},
        )
        application_service.submit_step(
            application, "credit_check", {"requested_amount": "50000", "iban": "SE3550000000054910000003"},
        )
        application_service.submit_step(application, "bank_verification", {})
        application.refresh_from_db()
        application_service.finalize_application(application)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.Status.REJECTED)
        self.assertIn("Confirmed sanctions/PEP match", application.decision_reasons)


class ResumeTokenTests(TestCase):
    def test_resume_with_valid_token_succeeds(self):
        application, token = application_service.start_application("PL", "individual")
        resumed = application_service.resume_application(token)
        self.assertEqual(resumed.id, application.id)

    def test_resume_with_invalid_token_raises(self):
        application_service.start_application("PL", "individual")
        with self.assertRaises(ApplicationFlowError):
            application_service.resume_application("not-a-real-token")

    def test_resume_with_expired_token_marks_expired_and_raises(self):
        application, token = application_service.start_application("PL", "individual")
        application.resume_token_expires_at = timezone.now() - timezone.timedelta(hours=1)
        application.save(update_fields=["resume_token_expires_at"])
        with self.assertRaises(ApplicationFlowError):
            application_service.resume_application(token)
        application.refresh_from_db()
        self.assertEqual(application.status, Application.Status.EXPIRED)

    def test_resume_logs_audit_event(self):
        application, token = application_service.start_application("PL", "individual")
        application_service.resume_application(token)
        self.assertTrue(
            AuditEvent.objects.filter(application=application, event_type="resumed").exists()
        )
