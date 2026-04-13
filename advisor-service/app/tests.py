from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.services.features import build_behavior_features


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
