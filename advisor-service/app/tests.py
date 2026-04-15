import importlib
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.services.behavior_dataset import BehaviorDatasetSchema
from app.services.features import (
    encode_behavior_label,
    export_behavior_dataset_metadata,
    vectorize_behavior_features,
)


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


class BehaviorDatasetSchemaTests(TestCase):
    def test_schema_orders_features_and_labels_deterministically(self):
        schema = BehaviorDatasetSchema.from_rows(
            [
                {"order_count": 1, "category_3_count": 2, "label": "tech_reader"},
                {"order_count": 2, "publisher_9_count": 1, "label": "casual_buyer"},
            ]
        )

        self.assertEqual(
            schema.feature_names,
            ["category_3_count", "order_count", "publisher_9_count"],
        )
        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])
        self.assertEqual(
            schema.vectorize_features({"order_count": 4, "category_3_count": 7}),
            [7.0, 4.0, 0.0],
        )
        self.assertEqual(schema.encode_label("tech_reader"), 1)

    def test_feature_helpers_export_schema_metadata(self):
        schema = BehaviorDatasetSchema(
            feature_names=["category_3_count", "order_count"],
            labels=["casual_buyer", "tech_reader"],
        )

        self.assertEqual(
            vectorize_behavior_features(schema, {"order_count": 5}),
            [0.0, 5.0],
        )
        self.assertEqual(encode_behavior_label(schema, "casual_buyer"), 0)
        self.assertEqual(
            export_behavior_dataset_metadata(schema),
            {
                "feature_names": ["category_3_count", "order_count"],
                "labels": ["casual_buyer", "tech_reader"],
                "feature_count": 2,
                "label_count": 2,
            },
        )
