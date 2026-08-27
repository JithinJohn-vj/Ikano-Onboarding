from django.test import SimpleTestCase

from onboarding.flows.definitions import get_flow
from onboarding.services.validation import StepValidationError, validate_step


class ValidationTests(SimpleTestCase):
    def setUp(self):
        self.identity_step = get_flow("SE", "individual").get_step("identity")
        self.financials_step = get_flow("SE", "individual").get_step("financials")

    def test_valid_submission_passes(self):
        cleaned = validate_step(
            self.identity_step,
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        self.assertEqual(cleaned["national_id"], "198506122384")

    def test_missing_required_field_raises(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(self.identity_step, {"full_name": "", "national_id": "", "date_of_birth": ""})
        self.assertIn("full_name", ctx.exception.errors)
        self.assertIn("national_id", ctx.exception.errors)

    def test_national_id_pattern_is_enforced_per_country(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.identity_step,
                {"full_name": "Anna Andersson", "national_id": "not-a-real-id", "date_of_birth": "1985-06-12"},
            )
        self.assertIn("national_id", ctx.exception.errors)

    def test_future_date_of_birth_rejected(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.identity_step,
                {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "2999-01-01"},
            )
        self.assertIn("date_of_birth", ctx.exception.errors)

    def test_number_field_min_value_enforced(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.financials_step,
                {
                    "employment_status": "employed",
                    "monthly_income": "-500",
                    "monthly_housing_cost": "9000",
                    "dependants": "1", "monthly_other_living_costs": "1000",
                    "monthly_debt_payments": "0", "employment_months": "12",
                },
            )
        self.assertIn("monthly_income", ctx.exception.errors)

    def test_select_field_rejects_value_outside_choices(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.financials_step,
                {
                    "employment_status": "on_a_boat",
                    "monthly_income": "30000",
                    "monthly_housing_cost": "9000",
                    "dependants": "1", "monthly_other_living_costs": "1000",
                    "monthly_debt_payments": "0", "employment_months": "12",
                },
            )
        self.assertIn("employment_status", ctx.exception.errors)

    def test_letters_in_phone_number_rejected(self):
        contact_step = get_flow("SE", "individual").get_step("contact")
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                contact_step,
                {
                    "email": "anna@example.com", "phone": "notaphonenumber",
                    "street_address": "Storgatan One", "postal_code": "11122",
                    "city": "Stockholm", "region": "Stockholm",
                },
            )
        self.assertIn("phone", ctx.exception.errors)

    def test_valid_phone_number_with_country_code_accepted(self):
        contact_step = get_flow("SE", "individual").get_step("contact")
        cleaned = validate_step(
            contact_step,
            {
                "email": "anna@example.com", "phone": "+46 70 123 45 67",
                "street_address": "Storgatan One", "postal_code": "11122",
                "city": "Stockholm", "region": "Stockholm",
            },
        )
        self.assertEqual(cleaned["phone"], "+46 70 123 45 67")

    def test_garbage_email_rejected(self):
        contact_step = get_flow("SE", "individual").get_step("contact")
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                contact_step,
                {
                    "email": "not-an-email", "phone": "+46701234567",
                    "street_address": "Storgatan One", "postal_code": "11122",
                    "city": "Stockholm", "region": "Stockholm",
                },
            )
        self.assertIn("email", ctx.exception.errors)

    def test_numbers_in_name_field_rejected(self):
        identity_step = get_flow("SE", "individual").get_step("identity")
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                identity_step,
                {"full_name": "Anna123", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
            )
        self.assertIn("full_name", ctx.exception.errors)

    def test_non_numeric_number_field_rejected(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.financials_step,
                {
                    "employment_status": "employed",
                    "monthly_income": "lots",
                    "monthly_housing_cost": "9000",
                    "dependants": "1", "monthly_other_living_costs": "1000",
                    "monthly_debt_payments": "0", "employment_months": "12",
                },
            )
        self.assertIn("monthly_income", ctx.exception.errors)

    def test_postal_codes_reject_letters_for_every_country(self):
        valid_postcodes = {"SE": "111 22", "ES": "28013", "PL": "00-001"}
        for country, valid_postcode in valid_postcodes.items():
            contact_step = get_flow(country, "individual").get_step("contact")
            valid_data = {
                "email": "anna@example.com", "phone": "+46701234567",
                "street_address": "Storgatan One", "postal_code": valid_postcode,
                "city": "Stockholm", "region": "Stockholm",
            }
            self.assertEqual(validate_step(contact_step, valid_data)["postal_code"], valid_postcode)

            invalid_data = dict(valid_data, postal_code="ABC12")
            with self.assertRaises(StepValidationError) as ctx:
                validate_step(contact_step, invalid_data)
            self.assertIn("postal_code", ctx.exception.errors)

    def test_number_fields_reject_not_a_number_and_infinity(self):
        base_data = {
            "employment_status": "employed",
            "monthly_income": "30000",
            "monthly_housing_cost": "9000",
            "dependants": "1", "monthly_other_living_costs": "1000",
            "monthly_debt_payments": "0", "employment_months": "12",
        }
        for invalid_value in ("NaN", "Infinity", "-Infinity"):
            with self.assertRaises(StepValidationError) as ctx:
                validate_step(self.financials_step, dict(base_data, monthly_income=invalid_value))
            self.assertIn("monthly_income", ctx.exception.errors)

    def test_dependants_must_be_a_whole_number(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.financials_step,
                {
                    "employment_status": "employed",
                    "monthly_income": "30000",
                    "monthly_housing_cost": "9000",
                    "dependants": "1.5", "monthly_other_living_costs": "1000",
                    "monthly_debt_payments": "0", "employment_months": "12",
                },
            )
        self.assertIn("dependants", ctx.exception.errors)

    def test_street_address_rejects_invalid_characters(self):
        contact_step = get_flow("SE", "individual").get_step("contact")
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                contact_step,
                {
                    "email": "anna@example.com", "phone": "+46701234567",
                    "street_address": "<script>alert(1)</script>", "postal_code": "11122",
                    "city": "Stockholm", "region": "Stockholm",
                },
            )
        self.assertIn("street_address", ctx.exception.errors)

    def test_street_address_rejects_numbers(self):
        contact_step = get_flow("SE", "individual").get_step("contact")
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                contact_step,
                {
                    "email": "anna@example.com", "phone": "+46701234567",
                    "street_address": "Storgatan 1", "postal_code": "11122",
                    "city": "Stockholm", "region": "Stockholm",
                },
            )
        self.assertIn("street_address", ctx.exception.errors)

    def test_swedish_personnummer_requires_twelve_digits_without_a_dash(self):
        with self.assertRaises(StepValidationError) as ctx:
            validate_step(
                self.identity_step,
                {"full_name": "Anna Andersson", "national_id": "19850612-2384", "date_of_birth": "1985-06-12"},
            )
        self.assertIn("national_id", ctx.exception.errors)
