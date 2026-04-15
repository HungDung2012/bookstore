import importlib
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient


class AdvisorBaselineTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_service_modules_import_cleanly(self):
        modules = [
            "app.services.advisor",
            "app.services.features",
            "app.services.clients",
            "app.services.behavior_model",
            "app.services.knowledge_base",
            "app.services.retriever",
            "app.services.prompting",
            "app.views",
            "app.serializers",
            "advisor_service.settings",
            "advisor_service.urls",
        ]

        for module_name in modules:
            module = importlib.import_module(module_name)
            self.assertIsNotNone(module)

    def test_health_endpoint_returns_service_name(self):
        response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["service"], "advisor-service")

    @patch("app.services.advisor.AdvisorService.chat")
    def test_chat_endpoint_returns_service_payload(self, chat_mock):
        chat_mock.return_value = {
            "answer": "Try technical books.",
            "behavior_segment": "tech_reader",
            "recommended_books": [],
            "sources": [],
        }

        response = self.client.post(
            "/advisor/chat/",
            {"user_id": 1, "question": "Recommend books"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "tech_reader")
        chat_mock.assert_called_once_with(user_id=1, question="Recommend books")

    @patch("app.services.advisor.AdvisorService.chat")
    def test_chat_endpoint_allows_missing_user_id(self, chat_mock):
        chat_mock.return_value = {
            "answer": "Try our featured catalog.",
            "behavior_segment": "casual_buyer",
            "recommended_books": [],
            "sources": [],
            "feature_summary": "Predicted segment is casual_buyer from orders=0, reviews=0.",
        }

        response = self.client.post(
            "/advisor/chat/",
            {"question": "Recommend books"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        chat_mock.assert_called_once_with(user_id=None, question="Recommend books")

    def test_chat_endpoint_rejects_missing_question(self):
        response = self.client.post(
            "/advisor/chat/",
            {"user_id": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("question", response.json())

    @patch("app.services.advisor.AdvisorService.profile")
    def test_profile_endpoint_returns_behavior_segment(self, profile_mock):
        profile_mock.return_value = {
            "behavior_segment": "literature_reader",
            "feature_summary": "Frequent purchases in literature.",
        }

        response = self.client.get("/advisor/profile/4/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "literature_reader")
        profile_mock.assert_called_once_with(user_id=4)
