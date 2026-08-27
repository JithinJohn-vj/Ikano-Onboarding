from django.test import SimpleTestCase

from onboarding.flows.definitions import get_flow
from onboarding.services.redaction import mask_value, redact_step_data


class RedactionTests(SimpleTestCase):
    def test_mask_value_keeps_last_four_chars(self):
        self.assertEqual(mask_value("19850612-2384"), "*********2384")

    def test_mask_value_short_string_fully_masked(self):
        self.assertEqual(mask_value("ab"), "**")

    def test_redact_step_data_masks_only_sensitive_fields(self):
        step = get_flow("SE", "individual").get_step("identity")
        submitted = {
            "full_name": "Anna Andersson",
            "national_id": "19850612-2384",
            "date_of_birth": "1985-06-12",
        }
        redacted = redact_step_data(step.fields, submitted)
        self.assertEqual(redacted["full_name"], "Anna Andersson")
        self.assertEqual(redacted["national_id"], "*********2384")
        self.assertNotIn("1985-06-12", str(redacted["national_id"]))

    def test_redact_step_data_does_not_mutate_input(self):
        step = get_flow("SE", "individual").get_step("identity")
        submitted = {"full_name": "A", "national_id": "19850612-2384", "date_of_birth": "1985-06-12"}
        original = dict(submitted)
        redact_step_data(step.fields, submitted)
        self.assertEqual(submitted, original)
