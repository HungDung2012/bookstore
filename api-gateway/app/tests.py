from unittest.mock import Mock, patch

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


class GatewayAdvisorTests(TestCase):
    def setUp(self):
        self.client = Client()

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
