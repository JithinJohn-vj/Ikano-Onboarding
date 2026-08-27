from django.test import SimpleTestCase

from onboarding.flows.country_config import COUNTRIES
from onboarding.flows.definitions import FLOWS, get_flow


class FlowRegistryTests(SimpleTestCase):
    def test_all_six_flows_exist(self):
        expected = {
            (c, t) for c in ("SE", "ES", "PL") for t in ("individual", "business")
        }
        self.assertEqual(set(FLOWS.keys()), expected)

    def test_get_flow_unknown_combo_raises(self):
        with self.assertRaises(ValueError):
            get_flow("XX", "individual")

    def test_every_flow_ends_in_review_step(self):
        for flow in FLOWS.values():
            self.assertEqual(flow.steps[-1].kind, "review")

    def test_every_flow_has_consent_step(self):
        for flow in FLOWS.values():
            self.assertIn("consent", flow.step_keys())

    def test_step_keys_are_unique_within_a_flow(self):
        for flow in FLOWS.values():
            keys = flow.step_keys()
            self.assertEqual(len(keys), len(set(keys)))

    def test_business_flows_include_ubo_and_representative(self):
        for country in COUNTRIES:
            flow = get_flow(country, "business")
            self.assertIn("representative", flow.step_keys())
            self.assertIn("authority_check", flow.step_keys())
            self.assertIn("ubo", flow.step_keys())

    def test_individual_flows_include_sanctions_screening(self):
        for country in COUNTRIES:
            flow = get_flow(country, "individual")
            consent = flow.get_step("consent")
            self.assertEqual(consent.integration.check_type, "sanctions")

    def test_individual_flows_do_not_include_business_only_steps(self):
        for country in COUNTRIES:
            flow = get_flow(country, "individual")
            self.assertNotIn("ubo", flow.step_keys())
            self.assertNotIn("company", flow.step_keys())

    def test_next_step_walks_in_order_and_ends_at_none(self):
        flow = get_flow("SE", "individual")
        keys = flow.step_keys()
        current = flow.first_step()
        seen = [current.key]
        while True:
            nxt = flow.next_step(current.key)
            if nxt is None:
                break
            seen.append(nxt.key)
            current = nxt
        self.assertEqual(seen, keys)

    def test_country_specific_id_pattern_used_in_identity_field(self):
        se_flow = get_flow("SE", "individual")
        identity_step = se_flow.get_step("identity")
        national_id_field = next(f for f in identity_step.fields if f.name == "national_id")
        self.assertEqual(national_id_field.pattern, COUNTRIES["SE"].person_id_pattern)
