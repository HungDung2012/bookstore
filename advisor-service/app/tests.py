import io
import csv
import importlib
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from app.services import clients
from app.management.commands import prepare_behavior_data
from app.services.features import build_behavior_features, infer_behavior_label
from app.services.behavior_model import BehaviorModelService


class AdvisorApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

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

    def test_chat_endpoint_rejects_missing_user_id(self):
        response = self.client.post(
            "/advisor/chat/",
            {"question": "Recommend books"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("user_id", response.json())

    def test_chat_endpoint_rejects_missing_question(self):
        response = self.client.post(
            "/advisor/chat/",
            {"user_id": 1},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("question", response.json())

    def test_build_behavior_features_aggregates_orders_reviews_and_cart(self):
        profile = {"id": 7, "full_name": "Alice"}
        books = [
            {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
            {"id": 2, "title": "Poems", "price": "10.00", "category": 5, "publisher": 2},
        ]
        orders = [
            {
                "id": 1,
                "total_amount": "40.00",
                "items": [
                    {"book_id": 1, "quantity": 2, "unit_price": "20.00"},
                ],
            }
        ]
        reviews = [{"book_id": 1, "rating": 5}, {"book_id": 2, "rating": 3}]
        cart_items = [{"book_id": 2, "quantity": 1}]

        result = build_behavior_features(profile, books, orders, reviews, cart_items)

        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["total_spent"], 40.0)
        self.assertEqual(result["review_count"], 2)
        self.assertEqual(result["cart_item_count"], 1)
        self.assertEqual(result["category_3_count"], 2)

    def test_build_behavior_features_returns_zero_defaults_for_empty_inputs(self):
        result = build_behavior_features({}, [], [], [], [])

        self.assertIsNone(result["user_id"])
        self.assertEqual(result["order_count"], 0)
        self.assertEqual(result["total_spent"], 0.0)
        self.assertEqual(result["average_order_value"], 0.0)
        self.assertEqual(result["total_quantity"], 0)
        self.assertEqual(result["review_count"], 0)
        self.assertEqual(result["average_review_rating"], 0.0)
        self.assertEqual(result["cart_item_count"], 0)
        self.assertEqual(result["premium_interest_score"], 0.0)
        self.assertEqual(result["budget_interest_score"], 0.0)

    def test_build_behavior_features_skips_missing_book_references(self):
        profile = {"id": 7}
        books = [
            {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
        ]
        orders = [
            {
                "id": 1,
                "total_amount": "20.00",
                "items": [
                    {"book_id": 999, "quantity": 2, "unit_price": "20.00"},
                    {"book_id": 1, "quantity": 1, "unit_price": "20.00"},
                ],
            }
        ]

        result = build_behavior_features(profile, books, orders, [], [])

        self.assertEqual(result["order_count"], 1)
        self.assertEqual(result["total_spent"], 20.0)
        self.assertEqual(result["total_quantity"], 3)
        self.assertEqual(result["category_3_count"], 1)
        self.assertEqual(result["publisher_9_count"], 1)

    def test_build_behavior_features_uses_score_boundaries(self):
        books = [
            {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
        ]

        premium_result = build_behavior_features(
            {"id": 7},
            books,
            [{"id": 1, "total_amount": "18.00", "items": [{"book_id": 1, "quantity": 1}]}],
            [],
            [],
        )
        budget_result = build_behavior_features(
            {"id": 7},
            books,
            [{"id": 2, "total_amount": "12.00", "items": [{"book_id": 1, "quantity": 1}]}],
            [],
            [],
        )

        self.assertEqual(premium_result["premium_interest_score"], 1.0)
        self.assertEqual(premium_result["budget_interest_score"], 0.0)
        self.assertEqual(budget_result["premium_interest_score"], 0.0)
        self.assertEqual(budget_result["budget_interest_score"], 0.0)

    def test_infer_behavior_label_prefers_tech_reader_when_technical_category_dominates(self):
        features = {
            "order_count": 4,
            "total_spent": 120.0,
            "category_3_count": 8,
            "category_5_count": 1,
            "budget_interest_score": 0.0,
        }

        self.assertEqual(infer_behavior_label(features), "tech_reader")

    @patch("app.management.commands.prepare_behavior_data.UpstreamClient")
    def test_prepare_behavior_data_command_writes_to_app_path_independent_of_cwd(self, client_mock):
        client = client_mock.return_value
        client.get_books.return_value = [
            {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
            {"id": 2, "title": "Poems", "price": "10.00", "category": 5, "publisher": 2},
        ]
        client.get_user.return_value = {"id": 1}
        client.get_orders.return_value = [
            {"id": 1, "total_amount": "40.00", "items": [{"book_id": 1, "quantity": 2}]}
        ]
        client.get_reviews.return_value = [{"book_id": 1, "rating": 5}]
        client.get_cart.return_value = [{"book_id": 2, "quantity": 1}]

        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                call_command("prepare_behavior_data", verbosity=0)
                output_path = prepare_behavior_data.OUTPUT_PATH
                self.assertTrue(output_path.exists())

                with output_path.open("r", encoding="utf-8") as csvfile:
                    rows = list(csv.DictReader(csvfile))

                self.assertEqual(len(rows), 20)
                self.assertEqual(rows[0]["label"], "tech_reader")
            finally:
                if prepare_behavior_data.OUTPUT_PATH.exists():
                    prepare_behavior_data.OUTPUT_PATH.unlink()
                os.chdir(original_cwd)

    @patch("app.management.commands.prepare_behavior_data.UpstreamClient")
    def test_prepare_behavior_data_command_logs_skipped_user_and_continues(self, client_mock):
        client = client_mock.return_value
        client.get_books.return_value = [
            {"id": 1, "title": "Python 101", "price": "20.00", "category": 3, "publisher": 9},
            {"id": 2, "title": "Poems", "price": "10.00", "category": 5, "publisher": 2},
        ]
        client.get_user.side_effect = lambda user_id: (
            (_ for _ in ()).throw(Exception("boom")) if user_id == 2 else {"id": user_id}
        )
        client.get_orders.return_value = [
            {"id": 1, "total_amount": "40.00", "items": [{"book_id": 1, "quantity": 2}]}
        ]
        client.get_reviews.return_value = [{"book_id": 1, "rating": 5}]
        client.get_cart.return_value = [{"book_id": 2, "quantity": 1}]

        output = io.StringIO()
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp_dir:
            os.chdir(tmp_dir)
            try:
                call_command("prepare_behavior_data", verbosity=0, stdout=output)
                output_path = prepare_behavior_data.OUTPUT_PATH
                self.assertTrue(output_path.exists())

                with output_path.open("r", encoding="utf-8") as csvfile:
                    rows = list(csv.DictReader(csvfile))

                self.assertEqual(len(rows), 19)
                self.assertIn("Skipping user 2: boom", output.getvalue())
            finally:
                if prepare_behavior_data.OUTPUT_PATH.exists():
                    prepare_behavior_data.OUTPUT_PATH.unlink()
                os.chdir(original_cwd)

    def test_service_urls_are_normalized_from_env_values(self):
        overrides = {
            "BOOK_SERVICE_URL": "books.internal:9000/",
            "ORDER_SERVICE_URL": "https://orders.internal:9443/",
            "REVIEW_SERVICE_URL": "review-service:8000",
            "CART_SERVICE_URL": "http://cart.internal:7000/",
            "USER_SERVICE_URL": "user-service.local/",
        }

        with patch.dict(os.environ, overrides, clear=False):
            module = importlib.reload(clients)

            self.assertEqual(module.BOOK_SERVICE_URL, "http://books.internal:9000")
            self.assertEqual(module.ORDER_SERVICE_URL, "https://orders.internal:9443")
            self.assertEqual(module.REVIEW_SERVICE_URL, "http://review-service:8000")
            self.assertEqual(module.CART_SERVICE_URL, "http://cart.internal:7000")
            self.assertEqual(module.USER_SERVICE_URL, "http://user-service.local")

        importlib.reload(clients)

    @patch("app.services.behavior_model.load_model")
    def test_behavior_model_predict_returns_known_label(self, load_model_mock):
        fake_model = load_model_mock.return_value
        fake_model.predict.return_value = [[0.8, 0.1, 0.05, 0.03, 0.02]]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            model_path = tmp_path / "model_behavior.h5"
            features_path = tmp_path / "features.txt"
            labels_path = tmp_path / "labels.txt"

            model_path.write_text("stub", encoding="utf-8")
            features_path.write_text(
                "order_count\ntotal_spent\ncategory_3_count",
                encoding="utf-8",
            )
            labels_path.write_text(
                "\n".join(
                    [
                        "tech_reader",
                        "literature_reader",
                        "family_reader",
                        "bargain_hunter",
                        "casual_buyer",
                    ]
                ),
                encoding="utf-8",
            )

            service = BehaviorModelService(
                model_path=model_path,
                features_path=features_path,
                labels_path=labels_path,
            )
            result = service.predict(
                {
                    "order_count": 4,
                    "total_spent": 100.0,
                    "category_3_count": 9,
                }
            )

        self.assertEqual(result["behavior_segment"], "tech_reader")

    @patch("app.services.behavior_model.load_model")
    def test_behavior_model_predict_uses_labels_and_features_artifacts(self, load_model_mock):
        fake_model = load_model_mock.return_value
        fake_model.predict.return_value = [[0.7, 0.2, 0.05, 0.03, 0.02]]

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            model_path = tmp_path / "model_behavior.h5"
            features_path = tmp_path / "features.txt"
            labels_path = tmp_path / "labels.txt"

            model_path.write_text("stub", encoding="utf-8")
            features_path.write_text(
                "total_spent\norder_count\ncategory_3_count",
                encoding="utf-8",
            )
            labels_path.write_text(
                "\n".join(
                    [
                        "bargain_hunter",
                        "tech_reader",
                        "family_reader",
                        "literature_reader",
                        "casual_buyer",
                    ]
                ),
                encoding="utf-8",
            )

            service = BehaviorModelService(
                model_path=model_path,
                features_path=features_path,
                labels_path=labels_path,
            )
            result = service.predict(
                {
                    "order_count": 4,
                    "total_spent": 100.0,
                    "category_3_count": 9,
                }
            )

        self.assertEqual(result["behavior_segment"], "bargain_hunter")
        self.assertEqual(fake_model.predict.call_args.args[0].tolist(), [[100.0, 4.0, 9.0]])

    def test_behavior_model_predict_logs_warning_and_falls_back_when_features_missing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            model_path = tmp_path / "model_behavior.h5"
            labels_path = tmp_path / "labels.txt"

            model_path.write_text("stub", encoding="utf-8")
            labels_path.write_text(
                "\n".join(
                    [
                        "tech_reader",
                        "literature_reader",
                        "family_reader",
                        "bargain_hunter",
                        "casual_buyer",
                    ]
                ),
                encoding="utf-8",
            )

            service = BehaviorModelService(
                model_path=model_path,
                features_path=tmp_path / "missing_features.txt",
                labels_path=labels_path,
            )

            with self.assertLogs("app.services.behavior_model", level="WARNING") as logs:
                result = service.predict({"order_count": 4, "total_spent": 100.0})

        self.assertEqual(result["behavior_segment"], "casual_buyer")
        self.assertEqual(result["probabilities"], {})
        self.assertIn("features artifact missing", "\n".join(logs.output))
