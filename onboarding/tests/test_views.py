from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from onboarding.models import Application
from onboarding.services import application_service
from onboarding.views import SESSION_ACCESS_KEY


class StartViewTests(TestCase):
    def test_get_start_page(self):
        resp = self.client.get(reverse("start"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sweden")

    def test_post_creates_application_and_redirects_to_first_step(self):
        resp = self.client.post(reverse("start"), {"country": "SE", "account_type": "individual"})
        self.assertEqual(Application.objects.count(), 1)
        application = Application.objects.first()
        self.assertRedirects(resp, reverse("step", args=[application.id, "identity"]))

    def test_post_with_missing_selection_shows_error(self):
        resp = self.client.post(reverse("start"), {"country": "", "account_type": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Application.objects.count(), 0)

    def test_embedded_browser_null_origin_can_submit_with_a_valid_csrf_token(self):
        client = Client(enforce_csrf_checks=True, HTTP_HOST="127.0.0.1:8000")
        page = client.get(reverse("start"), HTTP_HOST="127.0.0.1:8000")
        csrf_token = page.cookies["csrftoken"].value

        response = client.post(
            reverse("start"),
            {"country": "SE", "account_type": "individual", "csrfmiddlewaretoken": csrf_token},
            HTTP_HOST="127.0.0.1:8000",
            HTTP_ORIGIN="null",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Application.objects.count(), 1)


class AccessControlTests(TestCase):
    def test_step_view_without_session_access_redirects_to_resume(self):
        application, _ = application_service.start_application("SE", "individual")
        other_client = self.client_class()  # fresh session, no access granted
        resp = other_client.get(reverse("step", args=[application.id, "identity"]))
        self.assertRedirects(resp, reverse("resume_entry"))

    def test_creator_session_can_access_its_own_application(self):
        resp = self.client.post(reverse("start"), {"country": "SE", "account_type": "individual"})
        application = Application.objects.first()
        follow = self.client.get(reverse("step", args=[application.id, "identity"]))
        self.assertEqual(follow.status_code, 200)


class StepSubmissionViewTests(TestCase):
    def setUp(self):
        self.client.post(reverse("start"), {"country": "SE", "account_type": "individual"})
        self.application = Application.objects.first()

    def test_valid_post_redirects_to_next_step(self):
        resp = self.client.post(
            reverse("step", args=[self.application.id, "identity"]),
            {"full_name": "Anna Andersson", "national_id": "198506122384", "date_of_birth": "1985-06-12"},
        )
        self.application.refresh_from_db()
        self.assertRedirects(resp, reverse("step", args=[self.application.id, self.application.current_step_key]))

    def test_invalid_post_rerenders_form_with_errors(self):
        resp = self.client.post(
            reverse("step", args=[self.application.id, "identity"]),
            {"full_name": "", "national_id": "", "date_of_birth": ""},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "required")


class ResumeFlowViewTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_resume_with_valid_token_grants_access_in_new_session(self):
        application, token = application_service.start_application("ES", "business")
        fresh_client = self.client_class()
        resp = fresh_client.get(reverse("resume_magic_link", args=[token]))
        self.assertRedirects(resp, reverse("step", args=[application.id, application.current_step_key]))

    def test_resume_with_bad_token_redirects_to_resume_entry_with_message(self):
        fresh_client = self.client_class()
        resp = fresh_client.get(reverse("resume_magic_link", args=["garbage-token"]), follow=True)
        self.assertRedirects(resp, reverse("resume_entry"))

    def test_resume_rotates_the_browser_session(self):
        application, token = application_service.start_application("ES", "business")
        session = self.client.session
        session["unrelated"] = "value"
        session.save()
        previous_session_key = session.session_key

        response = self.client.get(reverse("resume_magic_link", args=[token]))

        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(self.client.session.session_key, previous_session_key)
        self.assertIn(str(application.id), self.client.session[SESSION_ACCESS_KEY])

    @override_settings(RESUME_MAX_ATTEMPTS=2, RESUME_ATTEMPT_WINDOW_SECONDS=60)
    def test_resume_attempts_are_rate_limited(self):
        self.client.get(reverse("resume_magic_link", args=["invalid-one"]))
        self.client.get(reverse("resume_magic_link", args=["invalid-two"]))
        response = self.client.get(reverse("resume_magic_link", args=["invalid-three"]))
        self.assertEqual(response.status_code, 429)


class ReviewAccessTests(TestCase):
    def test_cannot_submit_review_before_reaching_review_step(self):
        application, _ = application_service.start_application("SE", "individual")
        session = self.client.session
        session[SESSION_ACCESS_KEY] = [str(application.id)]
        session.save()

        response = self.client.post(
            reverse("review", args=[application.id]), {"terms_accepted": "on"}
        )

        self.assertRedirects(
            response, reverse("step", args=[application.id, application.current_step_key]), fetch_redirect_response=False
        )
        application.refresh_from_db()
        self.assertEqual(application.status, Application.Status.IN_PROGRESS)
        self.assertEqual(application.integration_results.count(), 0)
