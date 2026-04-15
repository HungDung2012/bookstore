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

    @patch("app.views.requests.post")
    @patch("app.views.requests.get")
    def test_add_to_cart_uses_authenticated_customer_scope(self, get_mock, post_mock):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {"id": 1, "username": "alice", "role": "customer"}
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        cart_response = Mock(status_code=404)
        cart_response.json.return_value = {"error": "Cart not found"}
        get_mock.return_value = cart_response

        create_response = Mock(status_code=201)
        create_response.json.return_value = {"id": 8, "customer_id": 1}
        add_response = Mock(status_code=201)
        add_response.json.return_value = {"id": 4, "book_id": 7, "quantity": 3}
        post_mock.side_effect = [create_response, add_response]

        response = self.client.post(
            "/cart/add/",
            {"book_id": "7", "quantity": "3", "customer_id": "99"},
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/cart/1/")
        get_mock.assert_called_once_with("http://cart-service:8000/carts/1/", timeout=5)
        self.assertEqual(post_mock.call_count, 2)
        self.assertEqual(
            post_mock.call_args_list[0].kwargs["json"],
            {"customer_id": 1},
        )
        self.assertEqual(
            post_mock.call_args_list[1].kwargs["json"],
            {"customer_id": 1, "book_id": 7, "quantity": 3},
        )

    @patch("app.views.requests.post")
    @patch("app.views.requests.get")
    def test_checkout_submits_authenticated_customer_cart_to_order_service(self, get_mock, post_mock):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = {
            "id": 3,
            "username": "customer1",
            "role": "customer",
            "full_name": "Customer One",
            "phone": "0900000000",
            "address": "123 Main St",
        }
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        cart_response = Mock(status_code=200)
        cart_response.json.return_value = [
            {"id": 11, "book_id": 7, "quantity": 2, "book_title": "Dune", "book_price": "19.99"},
            {"id": 12, "book_id": 8, "quantity": 1, "book_title": "Sapiens", "book_price": "14.50"},
        ]
        get_mock.return_value = cart_response

        order_response = Mock(status_code=201)
        order_response.json.return_value = {"id": 44, "user_id": 3, "status": "pending"}
        post_mock.return_value = order_response

        response = self.client.post(
            "/checkout/",
            {
                "shipping_name": "Customer One",
                "shipping_phone": "0900000000",
                "shipping_address": "123 Main St",
                "payment_method": "cod",
                "note": "Leave at front desk",
            },
            secure=True,
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/orders/44/")
        get_mock.assert_called_once_with("http://cart-service:8000/carts/3/", timeout=5)
        post_mock.assert_called_once_with(
            "http://order-service:8000/orders/",
            json={
                "user_id": 3,
                "shipping_name": "Customer One",
                "shipping_phone": "0900000000",
                "shipping_address": "123 Main St",
                "note": "Leave at front desk",
                "payment_method": "cod",
                "items": [
                    {"book_id": 7, "quantity": 2, "book_title": "Dune", "unit_price": "19.99"},
                    {"book_id": 8, "quantity": 1, "book_title": "Sapiens", "unit_price": "14.50"},
                ],
            },
            timeout=10,
        )


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

    @patch("app.views.requests.get")
    def test_admin_dashboard_users_section_fetches_and_filters_real_users(self, get_mock):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        users_response = Mock(status_code=200)
        users_response.json.return_value = [
            {
                "id": 10,
                "username": "alice",
                "email": "alice@example.com",
                "full_name": "Alice Nguyen",
                "phone": "0900000001",
                "address": "123 Main St",
                "role": "customer",
                "is_active": True,
                "created_at": "2026-04-15T08:00:00Z",
            },
            {
                "id": 11,
                "username": "staff01",
                "email": "staff@example.com",
                "full_name": "Staff One",
                "phone": "0900000002",
                "address": "456 Main St",
                "role": "staff",
                "is_active": True,
                "created_at": "2026-04-15T09:00:00Z",
            },
            {
                "id": 12,
                "username": "inactive",
                "email": "inactive@example.com",
                "full_name": "Inactive User",
                "phone": "0900000003",
                "address": "789 Main St",
                "role": "customer",
                "is_active": False,
                "created_at": "2026-04-15T10:00:00Z",
            },
        ]
        get_mock.return_value = users_response

        response = self.client.get("/admin/dashboard/?section=users&q=alice&role=customer&status=active", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_users.html")
        self.assertContains(response, "Manage Users")
        self.assertContains(response, "Alice Nguyen")
        self.assertContains(response, "customer")
        self.assertContains(response, "Active")
        self.assertNotContains(response, "Staff One")
        self.assertNotContains(response, "Inactive User")
        get_mock.assert_called_once_with("http://user-service:8000/users/", timeout=5)

    @patch("app.views.requests.get")
    def test_admin_dashboard_products_section_fetches_and_filters_real_products(self, get_mock):
        self._set_user_session({"id": 1, "username": "admin", "role": "admin"})

        def fake_get(url, timeout=5):
            response = Mock()
            if url == "http://book-service:8000/books/":
                response.status_code = 200
                response.json.return_value = [
                    {
                        "id": 21,
                        "title": "Dune",
                        "author": "Frank Herbert",
                        "price": "18.99",
                        "stock": 45,
                        "category": 2,
                        "publisher": 4,
                    },
                    {
                        "id": 22,
                        "title": "Python Crash Course",
                        "author": "Eric Matthes",
                        "price": "29.99",
                        "stock": 4,
                        "category": 3,
                        "publisher": 5,
                    },
                    {
                        "id": 23,
                        "title": "The Pragmatic Programmer",
                        "author": "Andrew Hunt",
                        "price": "31.50",
                        "stock": 2,
                        "category": 3,
                        "publisher": 5,
                    },
                ]
                return response
            if url == "http://book-service:8000/categories/":
                response.status_code = 200
                response.json.return_value = [
                    {"id": 2, "name": "Science Fiction"},
                    {"id": 3, "name": "Programming"},
                ]
                return response
            if url == "http://book-service:8000/publishers/":
                response.status_code = 200
                response.json.return_value = [
                    {"id": 4, "name": "Del Rey"},
                    {"id": 5, "name": "No Starch Press"},
                ]
                return response
            raise AssertionError(f"Unexpected URL {url}")

        get_mock.side_effect = fake_get

        response = self.client.get("/admin/dashboard/?section=products&q=python&stock=low", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin_products.html")
        self.assertContains(response, "Manage Products")
        self.assertContains(response, "Python Crash Course")
        self.assertContains(response, "Programming")
        self.assertContains(response, "No Starch Press")
        self.assertContains(response, "Low stock")
        self.assertNotContains(response, "Dune")
        self.assertNotContains(response, "The Pragmatic Programmer")
        self.assertEqual(
            get_mock.call_count,
            3,
        )

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
            "probabilities": {"tech_reader": 0.88, "casual_buyer": 0.07},
            "recommended_books": [{"id": 1, "title": "Clean Code"}],
            "sources": [{"id": "segment_tech_reader", "title": "Advice for technology readers"}],
            "graph_facts": [{"id": "fact_tech", "statement": "Tech readers prefer programming books."}],
            "graph_paths": [{"nodes": ["segment:tech_reader", "category:programming"]}],
        }
        post_mock.return_value = gateway_response

        response = self.client.post(
            "/advisor/chat/",
            '{"question": "Recommend books"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["behavior_segment"], "tech_reader")
        self.assertIn("probabilities", payload)
        self.assertIn("recommended_books", payload)
        self.assertIn("sources", payload)
        self.assertIn("graph_facts", payload)
        self.assertIn("graph_paths", payload)
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
            "probabilities": {"tech_reader": 0.88},
            "recommended_books": [],
            "sources": [],
            "graph_facts": [],
            "graph_paths": [],
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
            "probabilities": {"tech_reader": 0.91},
            "recommended_books": [{"id": 1, "title": "Clean Code"}],
            "sources": [{"id": "segment_tech_reader", "title": "Advice for technology readers"}],
            "graph_facts": [{"id": "fact_tech", "statement": "Tech readers prefer programming books."}],
            "graph_paths": [{"nodes": ["segment:tech_reader", "category:programming"]}],
            "preferences": [],
        }
        get_mock.return_value = gateway_response

        response = self.client.get("/advisor/profile/", secure=True)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["user_id"], 11)
        self.assertIn("probabilities", payload)
        self.assertIn("recommended_books", payload)
        self.assertIn("sources", payload)
        self.assertIn("graph_facts", payload)
        self.assertIn("graph_paths", payload)
        get_mock.assert_called_once()
        self.assertEqual(
            get_mock.call_args.args[0],
            "http://advisor-service:8000/advisor/profile/11/",
        )

    @patch("app.views.requests.post")
    def test_advisor_chat_normalizes_missing_richer_fields(self, post_mock):
        gateway_response = Mock(status_code=200)
        gateway_response.json.return_value = {
            "answer": "Try technical books.",
            "behavior_segment": "tech_reader",
        }
        post_mock.return_value = gateway_response

        response = self.client.post(
            "/advisor/chat/",
            '{"question": "Recommend books"}',
            content_type="application/json",
            secure=True,
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["probabilities"], {})
        self.assertEqual(payload["recommended_books"], [])
        self.assertEqual(payload["sources"], [])
        self.assertEqual(payload["graph_facts"], [])
        self.assertEqual(payload["graph_paths"], [])

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


class GatewayShippingWorkflowTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _set_user_session(self, user):
        session = self.client.session
        session["token"] = "demo-token"
        session["user"] = user
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    @patch("app.views.requests.get")
    def test_customer_shipping_detail_fails_closed_when_order_cannot_be_loaded(self, get_mock):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        order_response = Mock(status_code=404)
        order_response.json.return_value = {"error": "Not found"}
        get_mock.return_value = order_response

        response = self.client.get("/shipping/44/", secure=True)

        self.assertEqual(response.status_code, 404)
        get_mock.assert_called_once_with("http://order-service:8000/orders/44/", timeout=5)

    @patch("app.views.requests.get")
    def test_customer_my_orders_page_uses_dedicated_template_and_tracking_links(self, get_mock):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        orders_response = Mock(status_code=200)
        orders_response.json.return_value = [
            {
                "id": 44,
                "user_id": 3,
                "status": "shipping",
                "created_at": "2026-04-15T10:00:00Z",
                "items": [{"book_id": 1, "quantity": 1, "book_title": "Dune", "unit_price": "19.99"}],
                "total_amount": "19.99",
            }
        ]
        get_mock.return_value = orders_response

        response = self.client.get("/my-orders/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "my_orders.html")
        self.assertContains(response, "Order #44")
        self.assertContains(response, "/orders/44/")
        self.assertContains(response, "/shipping/44/")
        get_mock.assert_called_once_with("http://order-service:8000/orders/?user_id=3", timeout=5)

    @patch("app.views.requests.get")
    def test_orders_page_reuses_customer_my_orders_template(self, get_mock):
        self._set_user_session({"id": 3, "username": "alice", "role": "customer"})

        orders_response = Mock(status_code=200)
        orders_response.json.return_value = []
        get_mock.return_value = orders_response

        response = self.client.get("/orders/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "my_orders.html")

    @patch("app.views.requests.get")
    def test_staff_order_page_shows_orders_needing_processing(self, get_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        orders_response = Mock(status_code=200)
        orders_response.json.return_value = [
            {
                "id": 91,
                "user_id": 3,
                "status": "pending",
                "created_at": "2026-04-15T10:00:00Z",
                "shipping_name": "Alice",
                "shipping_phone": "0900000000",
                "shipping_address": "123 Main St",
                "items": [{"book_id": 1, "quantity": 1, "book_title": "Dune", "unit_price": "19.99"}],
                "total_amount": "19.99",
            },
            {
                "id": 92,
                "user_id": 4,
                "status": "confirmed",
                "created_at": "2026-04-15T11:00:00Z",
                "shipping_name": "Bob",
                "shipping_phone": "0900000001",
                "shipping_address": "456 Main St",
                "items": [{"book_id": 2, "quantity": 2, "book_title": "Sapiens", "unit_price": "14.50"}],
                "total_amount": "29.00",
            },
            {
                "id": 93,
                "user_id": 5,
                "status": "shipping",
                "created_at": "2026-04-15T12:00:00Z",
                "shipping_name": "Carol",
                "shipping_phone": "0900000002",
                "shipping_address": "789 Main St",
                "items": [{"book_id": 3, "quantity": 1, "book_title": "Neuromancer", "unit_price": "12.00"}],
                "total_amount": "12.00",
            },
        ]
        get_mock.return_value = orders_response

        response = self.client.get("/staff/orders/", secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "staff_orders.html")
        self.assertContains(response, "Orders To Process")
        self.assertContains(response, "Order #91")
        self.assertContains(response, "Order #92")
        self.assertNotContains(response, "Order #93")
        get_mock.assert_called_once_with("http://order-service:8000/orders/", timeout=5)

    @patch("app.views.requests.put")
    @patch("app.views.requests.get")
    def test_staff_order_page_can_update_status_in_staff_workflow(self, get_mock, put_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        order_detail_response = Mock(status_code=200)
        order_detail_response.json.return_value = {"id": 91, "status": "pending"}
        get_mock.return_value = order_detail_response
        put_mock.return_value = Mock(
            status_code=200,
            json=Mock(return_value={"id": 91, "status": "confirmed"}),
        )

        response = self.client.post("/staff/orders/", {"order_id": "91", "status": "confirmed"}, secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/staff/orders/")
        put_mock.assert_called_once_with(
            "http://order-service:8000/orders/91/status/",
            json={"status": "confirmed"},
            headers={"X-Internal-Service-Token": "gateway-internal-token"},
            timeout=5,
        )
        get_mock.assert_called_once_with("http://order-service:8000/orders/91/", timeout=5)

    @patch("app.views.requests.post")
    @patch("app.views.requests.get")
    def test_staff_shipping_creation_rejects_nonexistent_order(self, get_mock, post_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        def fake_get(url, timeout=5, params=None):
            response = Mock()
            if url == "http://order-service:8000/orders/55/":
                response.status_code = 404
                response.json.return_value = {"error": "Not found"}
                return response
            if url == "http://order-service:8000/orders/":
                response.status_code = 200
                response.json.return_value = []
                return response
            if url == "http://shipping-service:8000/shipping/":
                response.status_code = 200
                response.json.return_value = []
                return response
            raise AssertionError(f"Unexpected URL {url}")

        get_mock.side_effect = fake_get

        response = self.client.post("/staff/shipping/", {"order_id": "55"}, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order not found.")
        post_mock.assert_not_called()

    @patch("app.views.requests.post")
    @patch("app.views.requests.get")
    def test_staff_shipping_creation_rejects_order_without_paid_status(self, get_mock, post_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        def fake_get(url, timeout=5, params=None):
            response = Mock()
            if url == "http://order-service:8000/orders/56/":
                response.status_code = 200
                response.json.return_value = {"id": 56, "status": "confirmed"}
                return response
            if url == "http://order-service:8000/orders/":
                response.status_code = 200
                response.json.return_value = [{"id": 56, "status": "confirmed", "shipping_name": "A", "shipping_phone": "1", "shipping_address": "X", "total_amount": "10.00"}]
                return response
            if url == "http://shipping-service:8000/shipping/":
                response.status_code = 200
                response.json.return_value = []
                return response
            raise AssertionError(f"Unexpected URL {url}")

        get_mock.side_effect = fake_get

        response = self.client.post("/staff/shipping/", {"order_id": "56"}, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Only paid orders can be moved into shipping.")
        post_mock.assert_not_called()

    @patch("app.views.requests.put")
    @patch("app.views.requests.patch")
    @patch("app.views.requests.get")
    def test_staff_shipping_update_rolls_back_when_order_sync_fails(self, get_mock, patch_mock, put_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        def fake_get(url, timeout=5, params=None):
            response = Mock()
            if url == "http://order-service:8000/orders/77/":
                response.status_code = 200
                response.json.return_value = {"id": 77, "status": "paid", "shipping_name": "A", "shipping_phone": "1", "shipping_address": "X", "total_amount": "10.00"}
                return response
            if url == "http://shipping-service:8000/shipping/" and params == {"order_id": 77}:
                response.status_code = 200
                response.json.return_value = [{"id": 8, "order_id": 77, "status": "packed", "tracking_code": "SHP-000008"}]
                return response
            raise AssertionError(f"Unexpected URL {url} params={params}")

        get_mock.side_effect = fake_get
        patch_mock.side_effect = [
            Mock(status_code=200, json=Mock(return_value={"id": 8, "order_id": 77, "status": "shipping", "tracking_code": "SHP-000008"})),
            Mock(status_code=200, json=Mock(return_value={"id": 8, "order_id": 77, "status": "packed", "tracking_code": "SHP-000008"})),
        ]
        put_mock.return_value = Mock(status_code=400, json=Mock(return_value={"error": "Cannot change from 'paid' to 'shipping'" }))

        response = self.client.post("/shipping/77/", {"status": "shipping"}, secure=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order status sync failed. Shipment change was rolled back.")
        self.assertEqual(patch_mock.call_count, 2)
        self.assertEqual(
            patch_mock.call_args_list[0].args[0],
            "http://shipping-service:8000/shipping/8/",
        )
        self.assertEqual(patch_mock.call_args_list[0].kwargs["json"], {"status": "shipping"})
        self.assertEqual(patch_mock.call_args_list[1].kwargs["json"], {"status": "packed"})
        self.assertEqual(
            put_mock.call_args.kwargs["headers"],
            {"X-Internal-Service-Token": "gateway-internal-token"},
        )

    @patch("app.views.requests.put")
    @patch("app.views.requests.patch")
    @patch("app.views.requests.get")
    def test_staff_can_move_shipment_from_pending_to_packed_without_order_sync(self, get_mock, patch_mock, put_mock):
        self._set_user_session({"id": 2, "username": "staff", "role": "staff"})

        def fake_get(url, timeout=5, params=None):
            response = Mock()
            if url == "http://order-service:8000/orders/78/":
                response.status_code = 200
                response.json.return_value = {"id": 78, "status": "paid", "shipping_name": "A", "shipping_phone": "1", "shipping_address": "X", "total_amount": "10.00"}
                return response
            if url == "http://shipping-service:8000/shipping/" and params == {"order_id": 78}:
                response.status_code = 200
                response.json.return_value = [{"id": 9, "order_id": 78, "status": "pending", "tracking_code": "SHP-000009"}]
                return response
            raise AssertionError(f"Unexpected URL {url} params={params}")

        get_mock.side_effect = fake_get
        patch_mock.return_value = Mock(status_code=200, json=Mock(return_value={"id": 9, "order_id": 78, "status": "packed", "tracking_code": "SHP-000009"}))

        response = self.client.post("/shipping/78/", {"status": "packed"}, secure=True)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/shipping/78/")
        patch_mock.assert_called_once_with(
            "http://shipping-service:8000/shipping/9/",
            json={"status": "packed"},
            timeout=5,
        )
        put_mock.assert_not_called()
