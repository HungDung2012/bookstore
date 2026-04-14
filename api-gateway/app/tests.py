from unittest.mock import Mock, patch

import requests
from django.conf import settings
from django.test import Client, TestCase


class GatewayAuthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_profile_rehydrates_user_from_token(self):
        session = self.client.session
        session["token"] = "demo-token"
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        verify_response = Mock(status_code=200)
        verify_response.json.return_value = {
            "user": {
                "id": 11,
                "username": "alice",
                "full_name": "Alice",
                "phone": "",
                "address": "",
                "role": "customer",
            }
        }

        with patch("app.views.requests.post", return_value=verify_response):
            response = self.client.get("/profile/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.session["user"]["id"], 11)

    def test_cart_view_blocks_other_users(self):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {"id": 1, "username": "alice", "role": "customer"}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        response = self.client.get("/cart/2/", secure=True)

        self.assertEqual(response.status_code, 403)


class GatewayDashboardRoutingTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _set_user_session(self, user):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = user
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def _assert_dashboard_endpoint_is_reachable(self, path, role):
        response = self.client.get(path, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{role.title()} dashboard")

    def test_dashboard_redirects_unauthenticated_users_to_login(self):
        response = self.client.get("/dashboard/", secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/login/")

    def test_dashboard_redirects_admin_users_to_admin_dashboard(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        response = self.client.get("/dashboard/", secure=True, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/admin/dashboard/", 302)])
        self.assertContains(response, "Admin dashboard")

    def test_dashboard_redirects_staff_users_to_staff_dashboard(self):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        response = self.client.get("/dashboard/", secure=True, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/staff/dashboard/", 302)])
        self.assertContains(response, "Staff dashboard")

    def test_dashboard_redirects_customer_users_to_customer_dashboard(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        response = self.client.get("/dashboard/", secure=True, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/customer/dashboard/", 302)])
        self.assertContains(response, "Customer dashboard")

    def test_admin_dashboard_endpoint_is_reachable_with_admin_session(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        self._assert_dashboard_endpoint_is_reachable("/admin/dashboard/", "admin")

    def test_staff_session_redirects_from_admin_dashboard_to_staff_dashboard(self):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        response = self.client.get("/admin/dashboard/", secure=True, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/staff/dashboard/", 302)])
        self.assertContains(response, "Staff dashboard")

    def test_customer_session_redirects_from_staff_dashboard_to_customer_dashboard(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        response = self.client.get("/staff/dashboard/", secure=True, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain, [("/customer/dashboard/", 302)])
        self.assertContains(response, "Customer dashboard")

    def test_staff_dashboard_endpoint_is_reachable_with_staff_session(self):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        self._assert_dashboard_endpoint_is_reachable("/staff/dashboard/", "staff")

    def test_customer_dashboard_endpoint_is_reachable_with_customer_session(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        self._assert_dashboard_endpoint_is_reachable("/customer/dashboard/", "customer")

    def test_admin_dashboard_navigation_shows_management_links(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        response = self.client.get("/admin/dashboard/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'href="/admin/dashboard/?section=users"',
            html=False,
        )
        self.assertContains(
            response,
            'href="/admin/dashboard/?section=products"',
            html=False,
        )
        self.assertContains(response, "Manage Users")
        self.assertContains(response, "Manage Products")
        self.assertNotContains(response, 'href="/profile/">\n                    <i class="fa-solid fa-users-gear"></i> Manage Users', html=False)
        self.assertNotContains(
            response,
            'href="/books/create/">\n                    <i class="fa-solid fa-boxes-stacked"></i> Manage Products',
            html=False,
        )
        self.assertNotContains(response, "My Cart")
        self.assertNotContains(response, "My Orders")
        self.assertNotContains(response, "AI Book Advisor")

    def test_admin_dashboard_placeholder_sections_render_under_admin_dashboard(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        users_response = self.client.get("/admin/dashboard/?section=users", secure=True)
        products_response = self.client.get("/admin/dashboard/?section=products", secure=True)

        self.assertEqual(users_response.status_code, 200)
        self.assertContains(users_response, "Manage Users")
        self.assertContains(products_response, "Manage Products")
        self.assertNotContains(users_response, "My Cart")
        self.assertNotContains(products_response, "My Orders")

    def test_customer_dashboard_navigation_shows_customer_links_and_advisor(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        response = self.client.get("/customer/dashboard/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Cart")
        self.assertContains(response, "My Orders")
        self.assertContains(response, "/cart/3/")
        self.assertNotContains(response, "Manage Users")
        self.assertNotContains(response, "Manage Products")
        self.assertContains(response, "AI Book Advisor")


class GatewayAdvisorTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("app.views.requests.get")
    def test_books_page_contains_ai_advisor_launcher(self, get_mock):
        books_response = Mock(status_code=200)
        books_response.json.return_value = []
        get_mock.return_value = books_response

        response = self.client.get("/books/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Book Advisor")
        self.assertContains(response, "advisor-chat-launcher")

    @patch("app.views.requests.post")
    def test_advisor_chat_proxy_returns_json(self, post_mock):
        gateway_response = Mock(status_code=200)
        gateway_response.json.return_value = {
            "answer": "Read more programming books.",
            "behavior_segment": "tech_reader",
            "recommended_books": [],
            "sources": [],
        }
        post_mock.return_value = gateway_response

        response = self.client.post(
            "/advisor/chat/",
            '{"question": "Recommend books"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "tech_reader")
        post_mock.assert_called_once()
        self.assertEqual(
            post_mock.call_args.kwargs["json"],
            {"question": "Recommend books", "user_id": None},
        )

    @patch("app.views.requests.post")
    def test_advisor_chat_accepts_browser_post_without_csrf_token(self, post_mock):
        browser_client = Client(enforce_csrf_checks=True)
        gateway_response = Mock(status_code=200)
        gateway_response.json.return_value = {
            "answer": "Read more programming books.",
            "behavior_segment": "tech_reader",
            "recommended_books": [],
            "sources": [],
        }
        post_mock.return_value = gateway_response

        response = browser_client.post(
            "/advisor/chat/",
            '{"question": "Recommend books"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "tech_reader")

    @patch("app.views.requests.post")
    def test_advisor_chat_rejects_malformed_json(self, post_mock):
        response = self.client.post(
            "/advisor/chat/",
            "{invalid json",
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Invalid JSON request body")
        post_mock.assert_not_called()

    @patch("app.views.requests.post")
    def test_advisor_chat_handles_non_json_upstream_response(self, post_mock):
        gateway_response = Mock(status_code=200)
        gateway_response.json.side_effect = ValueError("No JSON object could be decoded")
        post_mock.return_value = gateway_response

        response = self.client.post(
            "/advisor/chat/",
            '{"question": "Recommend books"}',
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Advisor service returned a non-JSON response")

    @patch("app.views.requests.get")
    def test_advisor_profile_requires_auth_and_proxies_user(self, get_mock):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {"id": 11, "username": "alice", "role": "customer"}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        gateway_response = Mock(status_code=200)
        gateway_response.json.return_value = {
            "user_id": 11,
            "behavior_segment": "tech_reader",
            "preferences": [],
        }
        get_mock.return_value = gateway_response

        response = self.client.get("/advisor/profile/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user_id"], 11)
        get_mock.assert_called_once()
        self.assertEqual(
            get_mock.call_args.args[0],
            "http://advisor-service:8000/advisor/profile/11/",
        )

    @patch("app.views.requests.get")
    def test_advisor_profile_requires_auth(self, get_mock):
        response = self.client.get("/advisor/profile/", secure=True)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "Authentication required")
        get_mock.assert_not_called()

    @patch("app.views.requests.get")
    def test_advisor_profile_handles_non_json_upstream_response(self, get_mock):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {"id": 11, "username": "alice", "role": "customer"}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        gateway_response = Mock(status_code=200)
        gateway_response.json.side_effect = ValueError("No JSON object could be decoded")
        get_mock.return_value = gateway_response

        response = self.client.get("/advisor/profile/", secure=True)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "Advisor service returned a non-JSON response")

    @patch("app.views.requests.get")
    def test_advisor_profile_handles_request_failure(self, get_mock):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {"id": 11, "username": "alice", "role": "customer"}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        get_mock.side_effect = requests.exceptions.Timeout("upstream timed out")

        response = self.client.get("/advisor/profile/", secure=True)

        self.assertEqual(response.status_code, 503)
        self.assertIn("Advisor service unavailable", response.json()["error"])
