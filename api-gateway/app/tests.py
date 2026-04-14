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

    def _assert_dashboard_endpoint_is_reachable(self, path, role, template_name):
        response = self.client.get(path, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"{role.title()} dashboard")
        self.assertTemplateUsed(response, template_name)

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

        self._assert_dashboard_endpoint_is_reachable("/admin/dashboard/", "admin", "dashboard_admin.html")

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

        self._assert_dashboard_endpoint_is_reachable("/staff/dashboard/", "staff", "dashboard_staff.html")

    def test_customer_dashboard_endpoint_is_reachable_with_customer_session(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        self._assert_dashboard_endpoint_is_reachable("/customer/dashboard/", "customer", "dashboard_customer.html")

    def test_admin_dashboard_renders_summary_cards(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        response = self.client.get("/admin/dashboard/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_admin.html")
        self.assertContains(response, "User Overview")
        self.assertContains(response, "Catalog Overview")
        self.assertContains(response, "Manage Users")
        self.assertContains(response, "Manage Products")
        self.assertNotContains(response, "Orders To Process")
        self.assertNotContains(response, "Recommended For You")

    def test_admin_dashboard_users_section_renders_distinct_state(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        response = self.client.get("/admin/dashboard/?section=users", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_admin.html")
        self.assertContains(response, "Manage Users")
        self.assertContains(response, "User management workspace")
        self.assertContains(response, "Review new registrations")
        self.assertNotContains(response, "Catalog management workspace")
        self.assertNotContains(response, "Update featured titles")

    def test_admin_dashboard_products_section_renders_distinct_state(self):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        response = self.client.get("/admin/dashboard/?section=products", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_admin.html")
        self.assertContains(response, "Manage Products")
        self.assertContains(response, "Catalog management workspace")
        self.assertContains(response, "Update featured titles")
        self.assertNotContains(response, "User management workspace")
        self.assertNotContains(response, "Review new registrations")

    def test_staff_dashboard_renders_operational_cards(self):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        response = self.client.get("/staff/dashboard/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_staff.html")
        self.assertContains(response, "Orders To Process")
        self.assertContains(response, "Shipping Queue")
        self.assertContains(response, "Inventory Alerts")
        self.assertNotContains(response, "Catalog Overview")
        self.assertNotContains(response, "Recommended For You")

    def test_customer_dashboard_renders_customer_facing_overview(self):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        response = self.client.get("/customer/dashboard/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard_customer.html")
        self.assertContains(response, "Recommended For You")
        self.assertContains(response, "Reading Snapshot")
        self.assertContains(response, "My Cart")
        self.assertContains(response, "My Orders")
        self.assertContains(response, "/cart/3/")
        self.assertContains(response, "AI Book Advisor")
        self.assertNotContains(response, "Orders To Process")
        self.assertNotContains(response, "Manage Users")


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


class GatewayBookDetailTests(TestCase):
    def setUp(self):
        self.client = Client()

    @patch("app.views.requests.get")
    def test_book_detail_page_renders_catalog_information(self, get_mock):
        def fake_get(url, timeout=5):
            response = Mock()
            if url == "http://book-service:8000/books/7/":
                response.status_code = 200
                response.json.return_value = {
                    "id": 7,
                    "title": "Dune",
                    "author": "Frank Herbert",
                    "price": "18.99",
                    "stock": 45,
                    "category": 2,
                    "publisher": 4,
                }
                return response
            if url == "http://book-service:8000/categories/":
                response.status_code = 200
                response.json.return_value = [
                    {"id": 1, "name": "Classic Literature"},
                    {"id": 2, "name": "Science Fiction"},
                ]
                return response
            if url == "http://book-service:8000/publishers/":
                response.status_code = 200
                response.json.return_value = [
                    {"id": 3, "name": "Vintage Books"},
                    {"id": 4, "name": "Del Rey"},
                ]
                return response
            if url == "http://review-service:8000/reviews/?book_id=7":
                response.status_code = 200
                response.json.return_value = []
                return response
            if url == "http://review-service:8000/reviews/rating/7/":
                response.status_code = 200
                response.json.return_value = {"average_rating": 4.6, "total_reviews": 12}
                return response
            raise AssertionError(f"Unexpected URL {url}")

        get_mock.side_effect = fake_get

        response = self.client.get("/books/7/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "book_detail.html")
        self.assertContains(response, "Dune")
        self.assertContains(response, "Frank Herbert")
        self.assertContains(response, "$18.99")
        self.assertContains(response, "45 in stock")
        self.assertContains(response, "Science Fiction")
        self.assertContains(response, "Del Rey")
