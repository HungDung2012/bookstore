import json
import importlib
import csv
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from app.services.advisor import AdvisorService
from app.management.commands import train_behavior_model as train_behavior_model_module
from app.services.behavior_dataset import (
    BehaviorDatasetSchema,
    BehaviorSequenceSchema,
    generate_behavior_sequence_rows,
)
from app.services.behavior_model import BehaviorModelService
from app.services.features import build_behavior_features
from app.services.graph_kb import GraphEdge, GraphFact, GraphKnowledgeBase, GraphNode, Neo4jGraphService
from app.services.graph_retriever import GraphRetriever
from app.services.knowledge_base import KnowledgeBaseService
from app.services.rag_pipeline import HybridRAGPipeline
from app.services.prompting import build_chat_prompt, build_fallback_answer
from app.services.text_retriever import TextRetriever


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
            "probabilities": {"tech_reader": 0.81, "casual_buyer": 0.11},
            "recommended_books": [{"id": 1, "title": "Clean Code"}],
            "sources": [{"id": "faq_shipping_policy", "title": "Shipping policy"}],
            "graph_facts": [{"id": "fact_shipping", "statement": "Shipping updates matter."}],
            "graph_paths": [{"nodes": ["segment:tech_reader", "service:shipping"]}],
        }

        response = self.client.post(
            "/advisor/chat/",
            {"user_id": 1, "question": "Recommend books"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "tech_reader")
        self.assertIn("graph_facts", response.json())
        self.assertIn("graph_paths", response.json())
        chat_mock.assert_called_once_with(user_id=1, question="Recommend books")

    @patch("app.services.advisor.AdvisorService.chat")
    def test_chat_endpoint_allows_missing_user_id(self, chat_mock):
        chat_mock.return_value = {
            "answer": "Try our featured catalog.",
            "behavior_segment": "casual_buyer",
            "probabilities": {},
            "recommended_books": [],
            "sources": [],
            "graph_facts": [],
            "graph_paths": [],
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
            "probabilities": {"literature_reader": 0.74, "casual_buyer": 0.18},
            "recommended_books": [{"id": 2, "title": "Novel Study"}],
            "sources": [{"id": "segment_literature_reader", "title": "Advice for literature readers"}],
            "graph_facts": [{"id": "fact_literature", "statement": "Literature readers enjoy novels."}],
            "graph_paths": [{"nodes": ["segment:literature_reader", "category:literature"]}],
            "feature_summary": "Frequent purchases in literature.",
        }

        response = self.client.get("/advisor/profile/4/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["behavior_segment"], "literature_reader")
        self.assertIn("probabilities", response.json())
        self.assertIn("recommended_books", response.json())
        self.assertIn("graph_facts", response.json())
        self.assertIn("graph_paths", response.json())
        profile_mock.assert_called_once_with(user_id=4)

    @patch("app.services.advisor.AdvisorService.profile")
    def test_profile_endpoint_returns_richer_contract(self, profile_mock):
        profile_mock.return_value = {
            "behavior_segment": "tech_reader",
            "probabilities": {"tech_reader": 0.92},
            "recommended_books": [{"id": 1, "title": "Clean Code"}],
            "sources": [{"id": "segment_tech_reader", "title": "Advice for technology readers"}],
            "graph_facts": [{"id": "fact_tech", "statement": "Tech readers prefer programming books."}],
            "graph_paths": [{"nodes": ["segment:tech_reader", "category:programming"]}],
            "feature_summary": "Top probabilities: tech_reader=0.92.",
        }

        response = self.client.get("/advisor/profile/4/")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["behavior_segment"], "tech_reader")
        self.assertEqual(payload["probabilities"], {"tech_reader": 0.92})
        self.assertTrue(payload["recommended_books"])
        self.assertTrue(payload["sources"])
        self.assertTrue(payload["graph_facts"])
        self.assertTrue(payload["graph_paths"])
        profile_mock.assert_called_once_with(user_id=4)


class AdvisorServiceOrchestrationTests(TestCase):
    def setUp(self):
        self.service = AdvisorService()

        class FakeClient:
            def get_books(self):
                return [
                    {"id": 1, "title": "Clean Code", "category": 3, "price": "29.99"},
                    {"id": 2, "title": "Novel Study", "category": 5, "price": "19.99"},
                    {"id": 3, "title": "Kids Story", "category": 7, "price": "14.99"},
                ]

            def get_user(self, user_id):
                return {"id": user_id, "name": "Test User"}

            def get_orders(self, user_id):
                return [
                    {
                        "id": 101,
                        "total_amount": 58.0,
                        "items": [{"book_id": 1, "quantity": 1}],
                    }
                ]

            def get_reviews(self, user_id):
                return [{"id": 201, "rating": 5, "comment": "Great technical books."}]

            def get_cart(self, user_id):
                return [{"book_id": 1, "quantity": 1}]

        class FakeModelService:
            def predict(self, features):
                return {
                    "behavior_segment": "impulse_buyer",
                    "probabilities": {
                        "impulse_buyer": 0.81,
                        "window_shopper": 0.11,
                        "careful_researcher": 0.08,
                    },
                    "model_name": "bilstm",
                    "sequence_summary": {
                        "model_name": "bilstm",
                        "sequence_length": 8,
                        "feature_dim": 12,
                        "profile_fields": ["age_group", "favorite_category", "price_sensitivity", "membership_tier"],
                        "step_fields": [
                            *[f"step_{index}_behavior" for index in range(1, 9)],
                            *[f"step_{index}_category" for index in range(1, 9)],
                            *[f"step_{index}_price_band" for index in range(1, 9)],
                            *[f"step_{index}_duration" for index in range(1, 9)],
                        ],
                        "encoder_available": True,
                    },
                }

        self.service.client = FakeClient()
        self.service.model_service = FakeModelService()
        self.service._call_llm = lambda prompt: None

    def test_pick_books_routes_current_sequence_segments(self):
        books = [
            {"id": 1, "title": "Clean Code", "category": 3, "price": "29.99"},
            {"id": 2, "title": "Novel Study", "category": 5, "price": "19.99"},
            {"id": 3, "title": "Budget Guide", "category": 7, "price": "9.99"},
            {"id": 4, "title": "Business Basics", "category": 8, "price": "24.99"},
        ]

        impulse = self.service._pick_books(books, "impulse_buyer", limit=3)
        careful = self.service._pick_books(books, "careful_researcher", limit=3)
        discount = self.service._pick_books(books, "discount_hunter", limit=3)
        loyal = self.service._pick_books(books, "loyal_reader", limit=3)
        window = self.service._pick_books(books, "window_shopper", limit=3)

        self.assertEqual(impulse[0]["category"], 3)
        self.assertEqual(careful[0]["category"], 5)
        self.assertEqual(discount[0]["title"], "Budget Guide")
        self.assertEqual(loyal[0]["category"], 5)
        self.assertEqual(window[0]["category"], 8)
        self.assertEqual(len(window), 3)

    def test_chat_returns_behavior_segment_graph_facts_text_sources_and_probabilities(self):
        result = self.service.chat(
            user_id=1,
            question="What books should I buy and how does shipping work?",
        )

        self.assertEqual(result["behavior_segment"], "impulse_buyer")
        self.assertEqual(result["model_name"], "bilstm")
        self.assertEqual(result["sequence_summary"]["sequence_length"], 8)
        self.assertIn("impulse_buyer", result["probabilities"])
        self.assertTrue(result["recommended_books"])
        self.assertTrue(result["sources"])
        self.assertTrue(result["graph_facts"])
        self.assertTrue(result["context_blocks"])
        self.assertIn("feature_summary", result)
        self.assertIn("cart_items=1", result["feature_summary"])
        self.assertTrue(any(book["title"] == "Clean Code" for book in result["recommended_books"]))
        self.assertTrue(any(fact["statement"] for fact in result["graph_facts"]))
        self.assertTrue(any(source["text"] for source in result["sources"]))

    def test_chat_returns_safe_fallback_when_orchestration_fails(self):
        with patch.object(self.service.rag_pipeline, "retrieve", side_effect=RuntimeError("rag failed")):
            result = self.service.chat(user_id=1, question="What books should I buy?")

        self.assertEqual(result["behavior_segment"], "casual_buyer")
        self.assertEqual(result["probabilities"], {})
        self.assertEqual(result["recommended_books"], [])
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["graph_facts"], [])
        self.assertEqual(result["graph_paths"], [])
        self.assertIn("cac dau sach noi bat cua nha sach", result["answer"])

    def test_profile_returns_enriched_summary_and_probabilities(self):
        result = self.service.profile(user_id=1)

        self.assertEqual(result["behavior_segment"], "impulse_buyer")
        self.assertEqual(result["model_name"], "bilstm")
        self.assertEqual(result["sequence_summary"]["model_name"], "bilstm")
        self.assertIn("probabilities", result)
        self.assertIn("recommended_books", result)
        self.assertIn("feature_summary", result)
        self.assertIn("Top probabilities:", result["feature_summary"])
        self.assertTrue(result["recommended_books"])

    def test_profile_fallback_payload_preserves_success_shape(self):
        with patch.object(self.service, "_collect_behavior_inputs", side_effect=RuntimeError("upstream failed")):
            result = self.service.profile(user_id=1)

        self.assertEqual(
            result,
            {
                "behavior_segment": "casual_buyer",
                "probabilities": {},
                "recommended_books": [],
                "sources": [],
                "graph_facts": [],
                "graph_paths": [],
                "context_blocks": [],
                "model_name": "fallback",
                "sequence_summary": {
                    "model_name": "fallback",
                    "sequence_length": 0,
                    "feature_dim": 0,
                    "profile_fields": [],
                    "step_fields": [],
                    "encoder_available": False,
                },
                "feature_summary": "Profile unavailable; using fallback behavior segment.",
            },
        )


class RuntimeSequenceFeatureTests(TestCase):
    def test_build_behavior_features_maps_live_data_to_sequence_fields(self):
        profile = {
            "id": 42,
            "age_group": "18-25",
            "favorite_category": "technology",
            "price_sensitivity": "high",
            "membership_tier": "gold",
        }
        books = [
            {"id": 1, "title": "Clean Code", "category": 3, "price": "29.99"},
            {"id": 2, "title": "Novel Study", "category": 5, "price": "19.99"},
        ]
        orders = [
            {
                "id": 101,
                "total_amount": 29.99,
                "items": [{"book_id": 1, "quantity": 1}],
            }
        ]
        reviews = [{"id": 201, "book_id": 1, "rating": 5, "comment": "Great fit."}]
        cart_items = [{"book_id": 2, "quantity": 2}]

        features = build_behavior_features(profile, books, orders, reviews, cart_items)

        self.assertEqual(features["user_id"], 42)
        self.assertEqual(features["age_group"], "18-25")
        self.assertEqual(features["favorite_category"], "technology")
        self.assertEqual(features["price_sensitivity"], "high")
        self.assertEqual(features["membership_tier"], "gold")
        self.assertEqual(features["step_1_behavior"], "view_home")
        self.assertEqual(features["step_1_category"], "technology")
        self.assertEqual(features["step_2_behavior"], "search")
        self.assertEqual(features["step_2_category"], "technology")
        self.assertEqual(features["step_3_behavior"], "add_to_cart")
        self.assertEqual(features["step_4_behavior"], "checkout")
        self.assertEqual(features["step_5_behavior"], "review")
        self.assertEqual(features["step_8_behavior"], "view_home")
        self.assertIn("sequence_summary", features)
        self.assertEqual(features["sequence_summary"]["source_counts"]["orders"], 1)
        self.assertEqual(features["sequence_summary"]["source_counts"]["reviews"], 1)
        self.assertEqual(features["sequence_summary"]["source_counts"]["cart_items"], 1)

    def test_build_behavior_features_ignores_pending_orders_for_purchase_signals(self):
        profile = {
            "id": 42,
            "age_group": "18-25",
            "favorite_category": "technology",
            "price_sensitivity": "high",
            "membership_tier": "gold",
        }
        books = [
            {"id": 1, "title": "Clean Code", "category": 3, "price": "29.99", "publisher": 9},
            {"id": 2, "title": "Novel Study", "category": 5, "price": "19.99", "publisher": 10},
        ]
        orders = [
            {
                "id": 101,
                "status": "pending",
                "total_amount": 19.99,
                "items": [{"book_id": 2, "quantity": 1}],
            },
            {
                "id": 102,
                "status": "paid",
                "total_amount": 29.99,
                "items": [{"book_id": 1, "quantity": 1}],
            },
        ]

        features = build_behavior_features(profile, books, orders, reviews=[], cart_items=[])

        self.assertEqual(features["order_count"], 1)
        self.assertEqual(features["total_quantity"], 1)
        self.assertEqual(features["total_spent"], 29.99)
        self.assertEqual(features["category_3_count"], 1)
        self.assertNotIn("category_5_count", features)


class BehaviorDatasetSchemaTests(TestCase):
    def test_schema_handles_single_pass_iterables(self):
        def row_stream():
            yield {
                "user_id": 1,
                "order_count": 1,
                "category_3_count": 2,
                "label": " tech_reader ",
            }
            yield {
                "user_id": 2,
                "order_count": 2,
                "publisher_9_count": 1,
                "label": "casual_buyer",
            }

        schema = BehaviorDatasetSchema.from_rows(row_stream())

        self.assertEqual(
            schema.feature_names,
            ["category_3_count", "order_count", "publisher_9_count"],
        )
        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])

    def test_schema_normalizes_labels_with_whitespace(self):
        schema = BehaviorDatasetSchema.from_rows(
            [
                {"user_id": 1, "order_count": 1, "label": " tech_reader "},
                {"order_count": 2, "label": "casual_buyer"},
            ]
        )

        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])
        self.assertEqual(schema.encode_label(" tech_reader "), 1)

    def test_schema_exports_stable_columns_without_user_id(self):
        schema = BehaviorDatasetSchema.from_rows(
            [
                {"user_id": 9, "order_count": 1, "category_3_count": 2, "label": "tech_reader"},
                {"user_id": 11, "order_count": 2, "publisher_9_count": 1, "label": "casual_buyer"},
            ]
        )

        self.assertEqual(
            schema.feature_names,
            ["category_3_count", "order_count", "publisher_9_count"],
        )
        self.assertEqual(schema.export_fieldnames, ["category_3_count", "order_count", "publisher_9_count", "label"])
        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])
        self.assertEqual(
            schema.vectorize_features({"user_id": 42, "order_count": 4, "category_3_count": 7}),
            [7.0, 4.0, 0.0],
        )
        self.assertEqual(schema.encode_label("tech_reader"), 1)
        self.assertEqual(
            schema.build_record({"user_id": 42, "order_count": 4, "category_3_count": 7}, " tech_reader "),
            {"category_3_count": 7.0, "order_count": 4.0, "publisher_9_count": 0.0, "label": "tech_reader"},
        )


class BehaviorSequenceSchemaTests(TestCase):
    def test_schema_orders_sequence_steps_and_labels_deterministically(self):
        schema = BehaviorSequenceSchema.from_rows(
            [
                {
                    "user_id": 1,
                    "age_group": "18-25",
                    "favorite_category": "technology",
                    "price_sensitivity": "high",
                    "membership_tier": "gold",
                    "step_1_behavior": "browse",
                    "step_1_category": "technology",
                    "step_1_price_band": "low",
                    "step_1_duration": 12,
                    "step_2_behavior": "search",
                    "step_2_category": "technology",
                    "step_2_price_band": "mid",
                    "step_2_duration": 18,
                    "step_3_behavior": "compare",
                    "step_3_category": "technology",
                    "step_3_price_band": "mid",
                    "step_3_duration": 14,
                    "step_4_behavior": "cart",
                    "step_4_category": "technology",
                    "step_4_price_band": "high",
                    "step_4_duration": 11,
                    "step_5_behavior": "checkout",
                    "step_5_category": "technology",
                    "step_5_price_band": "high",
                    "step_5_duration": 8,
                    "step_6_behavior": "review",
                    "step_6_category": "technology",
                    "step_6_price_band": "high",
                    "step_6_duration": 5,
                    "step_7_behavior": "share",
                    "step_7_category": "technology",
                    "step_7_price_band": "mid",
                    "step_7_duration": 7,
                    "step_8_behavior": "return",
                    "step_8_category": "technology",
                    "step_8_price_band": "low",
                    "step_8_duration": 9,
                    "label": "impulse_buyer",
                },
                {
                    "user_id": 2,
                    "age_group": "26-35",
                    "favorite_category": "literature",
                    "price_sensitivity": "medium",
                    "membership_tier": "silver",
                    "step_1_behavior": "browse",
                    "step_1_category": "literature",
                    "step_1_price_band": "low",
                    "step_1_duration": 16,
                    "step_2_behavior": "search",
                    "step_2_category": "literature",
                    "step_2_price_band": "low",
                    "step_2_duration": 20,
                    "step_3_behavior": "compare",
                    "step_3_category": "literature",
                    "step_3_price_band": "mid",
                    "step_3_duration": 13,
                    "step_4_behavior": "wishlist",
                    "step_4_category": "literature",
                    "step_4_price_band": "mid",
                    "step_4_duration": 10,
                    "step_5_behavior": "cart",
                    "step_5_category": "literature",
                    "step_5_price_band": "high",
                    "step_5_duration": 15,
                    "step_6_behavior": "checkout",
                    "step_6_category": "literature",
                    "step_6_price_band": "high",
                    "step_6_duration": 9,
                    "step_7_behavior": "review",
                    "step_7_category": "literature",
                    "step_7_price_band": "mid",
                    "step_7_duration": 6,
                    "step_8_behavior": "return",
                    "step_8_category": "literature",
                    "step_8_price_band": "low",
                    "step_8_duration": 8,
                    "label": "careful_researcher",
                },
            ]
        )

        self.assertEqual(
            schema.profile_fields,
            ["user_id", "age_group", "favorite_category", "price_sensitivity", "membership_tier"],
        )
        self.assertEqual(
            schema.step_fields,
            [
                *[f"step_{index}_behavior" for index in range(1, 9)],
                *[f"step_{index}_category" for index in range(1, 9)],
                *[f"step_{index}_price_band" for index in range(1, 9)],
                *[f"step_{index}_duration" for index in range(1, 9)],
            ],
        )
        self.assertEqual(
            schema.labels,
            [
                "impulse_buyer",
                "careful_researcher",
                "discount_hunter",
                "loyal_reader",
                "window_shopper",
            ],
        )
        self.assertEqual(
            schema.export_fieldnames,
            [
                "user_id",
                "age_group",
                "favorite_category",
                "price_sensitivity",
                "membership_tier",
                *[f"step_{index}_behavior" for index in range(1, 9)],
                *[f"step_{index}_category" for index in range(1, 9)],
                *[f"step_{index}_price_band" for index in range(1, 9)],
                *[f"step_{index}_duration" for index in range(1, 9)],
                "label",
            ],
        )
        self.assertEqual(schema.to_metadata()["profile_fields"], schema.profile_fields)
        self.assertEqual(schema.to_metadata()["step_fields"], schema.step_fields)
        self.assertEqual(schema.to_metadata()["sequence_length"], 8)
        self.assertEqual(schema.to_metadata()["label_family"], schema.labels)

    def test_schema_restricts_step_behavior_values_to_approved_vocabulary(self):
        row = generate_behavior_sequence_rows(user_count=1, step_count=8, seed=500)[0]
        schema = BehaviorSequenceSchema.from_rows([row])

        allowed_behaviors = {
            "view_home",
            "search",
            "view_detail",
            "add_to_cart",
            "remove_from_cart",
            "wishlist",
            "checkout",
            "review",
        }
        record = schema.build_record(row, row["label"])
        behavior_fields = [field for field in schema.step_fields if field.endswith("_behavior")]
        self.assertTrue(all(record[field] in allowed_behaviors for field in behavior_fields))
        self.assertTrue(all(row[field] in allowed_behaviors for field in behavior_fields))

    def test_schema_does_not_leak_label_into_favorite_category(self):
        rows = generate_behavior_sequence_rows(user_count=20, step_count=8, seed=500)

        self.assertTrue(all(row["favorite_category"] != row["label"].replace("_", " ") for row in rows))

    def test_labels_do_not_cycle_with_user_order(self):
        rows = generate_behavior_sequence_rows(user_count=20, step_count=8, seed=500)
        expected_cycle = [BehaviorSequenceSchema.from_rows(rows).labels[index % 5] for index in range(20)]

        self.assertNotEqual([row["label"] for row in rows], expected_cycle)

    def test_each_label_produces_multiple_behavior_sequences(self):
        rows = generate_behavior_sequence_rows(user_count=500, step_count=8, seed=500)
        schema = BehaviorSequenceSchema.from_rows(rows)
        behavior_fields = [field for field in schema.step_fields if field.endswith("_behavior")]

        by_label = {}
        for row in rows:
            by_label.setdefault(row["label"], set()).add(tuple(row[field] for field in behavior_fields))

        self.assertTrue(all(len(sequences) > 1 for sequences in by_label.values()))


class PrepareBehaviorDataTests(TestCase):
    def test_prepare_behavior_data_writes_sequence_dataset_sample_and_metadata(self):
        from app.management.commands import prepare_behavior_data as prepare_behavior_data_module

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "data_user500.csv"
            sample_path = Path(tmpdir) / "data_user500_sample20.csv"
            metadata_path = Path(tmpdir) / "data_user500_metadata.json"

            with patch.object(prepare_behavior_data_module, "OUTPUT_PATH", output_path):
                prepare_behavior_data_module.Command().handle()

            with output_path.open("r", encoding="utf-8", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                fieldnames = reader.fieldnames

            with sample_path.open("r", encoding="utf-8", newline="") as csvfile:
                sample_rows = list(csv.DictReader(csvfile))

            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        self.assertIsNotNone(fieldnames)
        self.assertEqual(fieldnames, BehaviorSequenceSchema.from_rows(rows).export_fieldnames)
        self.assertEqual(len(rows), 500)
        self.assertEqual(len(sample_rows), 20)
        self.assertEqual(metadata["user_count"], 500)
        self.assertEqual(metadata["sample_count"], 20)
        self.assertEqual(metadata["sequence_length"], 8)
        self.assertEqual(
            metadata["profile_fields"],
            ["user_id", "age_group", "favorite_category", "price_sensitivity", "membership_tier"],
        )
        self.assertEqual(len(metadata["step_fields"]), 32)
        self.assertEqual(
            metadata["label_family"],
            [
                "impulse_buyer",
                "careful_researcher",
                "discount_hunter",
                "loyal_reader",
                "window_shopper",
            ],
        )
        self.assertEqual(metadata["dataset_file"], "data_user500.csv")
        self.assertEqual(metadata["sample_file"], "data_user500_sample20.csv")
        self.assertEqual(metadata["metadata_file"], "data_user500_metadata.json")
        self.assertEqual(rows[0]["user_id"], "1")
        self.assertIn("age_group", rows[0])
        self.assertIn("membership_tier", rows[0])
        self.assertIn("step_8_duration", rows[0])
        behavior_fields = [field for field in fieldnames if field.endswith("_behavior")]
        allowed_behaviors = {
            "view_home",
            "search",
            "view_detail",
            "add_to_cart",
            "remove_from_cart",
            "wishlist",
            "checkout",
            "review",
        }
        self.assertEqual(
            [key for key in rows[0].keys() if key.startswith("step_")],
            BehaviorSequenceSchema.from_rows(rows).step_fields,
        )
        self.assertTrue(all(row[field] in allowed_behaviors for row in rows for field in behavior_fields))
        self.assertTrue(all(row[field] in allowed_behaviors for row in sample_rows for field in behavior_fields))


class BehaviorModelDefinitionTests(TestCase):
    def test_build_behavior_model_returns_compiled_model(self):
        from app.services import behavior_model as behavior_model_module

        class FakeInput:
            def __init__(self, shape):
                self.shape = shape

        class FakeDense:
            def __init__(self, units, activation=None):
                self.units = units
                self.activation = activation

        class FakeDropout:
            def __init__(self, rate):
                self.rate = rate

        class FakeSequential:
            def __init__(self, layers):
                self.layers = layers
                self.input_shape = (None, layers[0].shape[0])
                dense_layers = [layer for layer in layers if hasattr(layer, "units")]
                self.output_shape = (None, dense_layers[-1].units)
                self.compile_kwargs = None

            def compile(self, **kwargs):
                self.compile_kwargs = kwargs

        with patch.object(behavior_model_module, "Sequential", FakeSequential), patch.object(
            behavior_model_module, "Dense", FakeDense
        ), patch.object(behavior_model_module, "Dropout", FakeDropout), patch.object(
            behavior_model_module, "Input", FakeInput
        ):
            model = behavior_model_module.build_behavior_model(input_dim=6, output_dim=3)

        self.assertEqual(model.input_shape[-1], 6)
        self.assertEqual(model.output_shape[-1], 3)
        self.assertEqual(model.compile_kwargs["loss"], "categorical_crossentropy")
        self.assertEqual(model.compile_kwargs["optimizer"], "adam")


class BehaviorModelMetadataTests(TestCase):
    def test_predict_falls_back_to_artifact_files_when_metadata_is_inconsistent(self):
        from app.services import behavior_model as behavior_model_module

        class FakeModel:
            def __init__(self):
                self.seen_vector = None

            def predict(self, vector, verbose=0):
                self.seen_vector = vector
                return [[0.8, 0.2]]

        fake_model = FakeModel()

        with TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            (model_dir / "model_behavior.h5").write_text("stub", encoding="utf-8")
            (model_dir / "features.txt").write_text("a\nb\n", encoding="utf-8")
            (model_dir / "labels.txt").write_text("yes\nno\n", encoding="utf-8")
            (model_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "feature_names": ["b", "a"],
                        "labels": ["no", "yes"],
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(behavior_model_module, "load_model", return_value=fake_model):
                service = BehaviorModelService(
                    model_path=model_dir / "model_behavior.h5",
                    features_path=model_dir / "features.txt",
                    labels_path=model_dir / "labels.txt",
                    metadata_path=model_dir / "metadata.json",
                )
                result = service.predict({"a": 1, "b": 2})

        self.assertEqual(result["behavior_segment"], "yes")
        self.assertEqual(fake_model.seen_vector.tolist(), [[1.0, 2.0]])
        self.assertEqual(service._load_feature_names(), ["a", "b"])
        self.assertEqual(service._load_labels(), ["yes", "no"])


class BehaviorSequenceTrainingTests(TestCase):
    def test_sequence_encoder_fits_training_rows_only(self):
        training_rows = [
            {
                "user_id": 1,
                "age_group": "18-25",
                "favorite_category": "technology",
                "price_sensitivity": "low",
                "membership_tier": "gold",
                **{f"step_{index}_{component}": value for index in range(1, 9) for component, value in [
                    ("behavior", "view_home"),
                    ("category", "technology"),
                    ("price_band", "low"),
                    ("duration", 8),
                ]},
                "label": "impulse_buyer",
            },
            {
                "user_id": 2,
                "age_group": "26-35",
                "favorite_category": "literature",
                "price_sensitivity": "medium",
                "membership_tier": "silver",
                **{f"step_{index}_{component}": value for index in range(1, 9) for component, value in [
                    ("behavior", "search"),
                    ("category", "literature"),
                    ("price_band", "mid"),
                    ("duration", 11),
                ]},
                "label": "careful_researcher",
            },
        ]
        validation_rows = [
            {
                "user_id": 3,
                "age_group": "36-45",
                "favorite_category": "rare_category",
                "price_sensitivity": "high",
                "membership_tier": "bronze",
                **{f"step_{index}_{component}": value for index in range(1, 9) for component, value in [
                    ("behavior", "view_detail"),
                    ("category", "rare_category"),
                    ("price_band", "high"),
                    ("duration", 17),
                ]},
                "label": "discount_hunter",
            }
        ]

        X_train, y_train, schema, encoder = train_behavior_model_module._encode_rows_with_encoder(training_rows)
        X_val, y_val, _, _ = train_behavior_model_module._encode_rows_with_encoder(
            validation_rows, schema=schema, encoder=encoder
        )

        self.assertEqual(X_train.shape[0], 2)
        self.assertEqual(X_val.shape[0], 1)
        self.assertEqual(y_train.shape, (2, len(schema.labels)))
        self.assertEqual(y_val.shape, (1, len(schema.labels)))
        self.assertNotIn("rare_category", encoder["profile_vocabs"]["favorite_category"])
        favorite_category_width = len(encoder["profile_vocabs"]["favorite_category"])
        age_group_width = len(encoder["profile_vocabs"]["age_group"])
        self.assertTrue(np.allclose(X_val[0, 0, age_group_width:age_group_width + favorite_category_width], 0.0))
        self.assertNotIn("user_id", train_behavior_model_module._sequence_feature_names_from_encoder(encoder))

    def test_select_best_model_prefers_f1_then_accuracy_then_bilstm(self):
        ranked_metrics = {
            "simple_rnn": {"f1_macro": 0.82, "accuracy": 0.91},
            "lstm": {"f1_macro": 0.82, "accuracy": 0.91},
            "bilstm": {"f1_macro": 0.82, "accuracy": 0.91},
        }

        self.assertEqual(train_behavior_model_module._select_best_model(ranked_metrics), "bilstm")

        ranked_metrics["lstm"]["accuracy"] = 0.95
        self.assertEqual(train_behavior_model_module._select_best_model(ranked_metrics), "lstm")

        ranked_metrics["simple_rnn"]["f1_macro"] = 0.99
        self.assertEqual(train_behavior_model_module._select_best_model(ranked_metrics), "simple_rnn")

    def test_model_selection_uses_validation_metrics_not_test_metrics(self):
        self.assertEqual(
            train_behavior_model_module._select_best_model_from_validation(
                {
                    "simple_rnn": {
                        "accuracy": 0.88,
                        "precision_macro": 0.87,
                        "recall_macro": 0.86,
                        "f1_macro": 0.86,
                    },
                    "lstm": {
                        "accuracy": 0.90,
                        "precision_macro": 0.90,
                        "recall_macro": 0.89,
                        "f1_macro": 0.90,
                    },
                    "bilstm": {
                        "accuracy": 0.90,
                        "precision_macro": 0.91,
                        "recall_macro": 0.90,
                        "f1_macro": 0.90,
                    },
                },
                {
                    "simple_rnn": {
                        "accuracy": 0.96,
                        "precision_macro": 0.95,
                        "recall_macro": 0.95,
                        "f1_macro": 0.95,
                    },
                    "lstm": {
                        "accuracy": 0.80,
                        "precision_macro": 0.79,
                        "recall_macro": 0.78,
                        "f1_macro": 0.78,
                    },
                    "bilstm": {
                        "accuracy": 0.79,
                        "precision_macro": 0.78,
                        "recall_macro": 0.77,
                        "f1_macro": 0.77,
                    },
                },
            ),
            "bilstm",
        )

        payload = train_behavior_model_module._build_comparison_payload(
            dataset_path=Path("advisor-service/app/data/training/data_user500.csv"),
            model_metrics={
                "simple_rnn": {
                    "accuracy": 0.88,
                    "precision_macro": 0.87,
                    "recall_macro": 0.86,
                    "f1_macro": 0.86,
                },
                "lstm": {
                    "accuracy": 0.90,
                    "precision_macro": 0.90,
                    "recall_macro": 0.89,
                    "f1_macro": 0.90,
                },
                "bilstm": {
                    "accuracy": 0.90,
                    "precision_macro": 0.91,
                    "recall_macro": 0.90,
                    "f1_macro": 0.90,
                },
            },
            best_model_name="bilstm",
        )

        self.assertEqual(payload["best_model_name"], "bilstm")
        self.assertEqual(payload["ranking"][0]["model_name"], "bilstm")
        self.assertEqual(payload["models"]["simple_rnn"]["f1_macro"], 0.86)

    def test_build_model_payload_includes_classification_metrics_and_confusion_matrix(self):
        payload = train_behavior_model_module._build_model_artifact_payload(
            model_name="lstm",
            metrics={
                "accuracy": 0.91,
                "precision_macro": 0.88,
                "recall_macro": 0.86,
                "f1_macro": 0.87,
            },
            labels=["a", "b"],
            confusion_matrix=[[3, 1], [0, 4]],
            classification_report={"accuracy": 0.91, "macro avg": {"f1-score": 0.87}},
        )

        self.assertEqual(payload["model_name"], "lstm")
        self.assertIn("metrics", payload)
        self.assertIn("confusion_matrix", payload)
        self.assertIn("classification_report", payload)
        self.assertEqual(payload["metrics"]["precision_macro"], 0.88)
        self.assertEqual(payload["metrics"]["recall_macro"], 0.86)
        self.assertEqual(payload["confusion_matrix"], [[3, 1], [0, 4]])

    def test_build_comparison_payload_records_selection_and_metric_ranking(self):
        payload = train_behavior_model_module._build_comparison_payload(
            dataset_path=Path("advisor-service/app/data/training/data_user500.csv"),
            best_model_name="bilstm",
            model_metrics={
                "simple_rnn": {
                    "accuracy": 0.88,
                    "precision_macro": 0.87,
                    "recall_macro": 0.86,
                    "f1_macro": 0.86,
                },
                "lstm": {
                    "accuracy": 0.91,
                    "precision_macro": 0.90,
                    "recall_macro": 0.89,
                    "f1_macro": 0.90,
                },
                "bilstm": {
                    "accuracy": 0.91,
                    "precision_macro": 0.91,
                    "recall_macro": 0.90,
                    "f1_macro": 0.90,
                },
            },
        )

        self.assertEqual(payload["best_model_name"], "bilstm")
        self.assertIn("ranking", payload)
        self.assertEqual(payload["ranking"][0]["model_name"], "bilstm")
        self.assertEqual(payload["models"]["lstm"]["precision_macro"], 0.90)

    def test_predict_uses_best_model_metadata_and_sequence_summary(self):
        from app.services import behavior_model as behavior_model_module

        class FakeModel:
            def __init__(self):
                self.seen_shape = None

            def predict(self, tensor, verbose=0):
                self.seen_shape = tuple(tensor.shape)
                return np.array([[0.05, 0.9, 0.01, 0.02, 0.02]])

        fake_model = FakeModel()
        row = generate_behavior_sequence_rows(user_count=1, step_count=8, seed=500)[0]

        with TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            (model_dir / "model_best.keras").write_text("stub", encoding="utf-8")
            (model_dir / "metadata.json").write_text(
                json.dumps(
                    {
                        "model_name": "bilstm",
                        "labels": [
                            "impulse_buyer",
                            "careful_researcher",
                            "discount_hunter",
                            "loyal_reader",
                            "window_shopper",
                        ],
                        "profile_fields": [
                            "age_group",
                            "favorite_category",
                            "price_sensitivity",
                            "membership_tier",
                        ],
                        "step_fields": [
                            *[f"step_{index}_behavior" for index in range(1, 9)],
                            *[f"step_{index}_category" for index in range(1, 9)],
                            *[f"step_{index}_price_band" for index in range(1, 9)],
                            *[f"step_{index}_duration" for index in range(1, 9)],
                        ],
                        "sequence_length": 8,
                        "feature_dim": 12,
                    }
                ),
                encoding="utf-8",
            )

            with patch.object(behavior_model_module, "load_model", return_value=fake_model):
                service = BehaviorModelService(
                    model_path=model_dir / "model_best.keras",
                    metadata_path=model_dir / "metadata.json",
                )
                result = service.predict(row)

        self.assertEqual(fake_model.seen_shape, (1, 8, 12))
        self.assertEqual(result["behavior_segment"], "careful_researcher")
        self.assertEqual(result["model_name"], "bilstm")
        self.assertIn("probabilities", result)
        self.assertIn("sequence_summary", result)
        self.assertEqual(result["sequence_summary"]["sequence_length"], 8)
        self.assertEqual(result["sequence_summary"]["feature_dim"], 12)

    def test_sequence_metadata_labels_override_stale_legacy_label_artifact(self):
        from app.services import behavior_model as behavior_model_module

        class FakeModel:
            def predict(self, tensor, verbose=0):
                return np.array([[0.1, 0.2, 0.7]])

        with TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir)
            (model_dir / "model_best.keras").write_text("stub", encoding="utf-8")
            (model_dir / "model_metadata.json").write_text(
                json.dumps(
                    {
                        "model_name": "bilstm",
                        "best_model_name": "bilstm",
                        "labels": ["metadata_a", "metadata_b", "metadata_c"],
                        "profile_fields": ["age_group", "favorite_category", "price_sensitivity", "membership_tier"],
                        "step_fields": [
                            *[f"step_{index}_behavior" for index in range(1, 9)],
                            *[f"step_{index}_category" for index in range(1, 9)],
                            *[f"step_{index}_price_band" for index in range(1, 9)],
                            *[f"step_{index}_duration" for index in range(1, 9)],
                        ],
                        "sequence_length": 8,
                        "feature_dim": 12,
                        "encoder": {
                            "profile_fields": ["age_group", "favorite_category", "price_sensitivity", "membership_tier"],
                            "step_components": ["behavior", "category", "price_band"],
                            "sequence_length": 8,
                            "feature_dim": 12,
                            "profile_vocabs": {
                                "age_group": ["18-25"],
                                "favorite_category": ["technology"],
                                "price_sensitivity": ["low"],
                                "membership_tier": ["gold"],
                            },
                            "step_vocabs": {
                                "behavior": ["view_home"],
                                "category": ["technology"],
                                "price_band": ["low"],
                            },
                            "duration": {"min": 1, "max": 18},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (model_dir / "labels.txt").write_text("legacy_a\nlegacy_b\nlegacy_c\n", encoding="utf-8")
            (model_dir / "features.txt").write_text("legacy_feature\n", encoding="utf-8")

            with patch.object(behavior_model_module, "load_model", return_value=FakeModel()):
                service = BehaviorModelService(
                    model_path=model_dir / "model_best.keras",
                    metadata_path=model_dir / "model_metadata.json",
                    labels_path=model_dir / "labels.txt",
                    features_path=model_dir / "features.txt",
                )
                result = service.predict(
                    {
                        "age_group": "18-25",
                        "favorite_category": "technology",
                        "price_sensitivity": "low",
                        "membership_tier": "gold",
                        **{f"step_{index}_behavior": "view_home" for index in range(1, 9)},
                        **{f"step_{index}_category": "technology" for index in range(1, 9)},
                        **{f"step_{index}_price_band": "low" for index in range(1, 9)},
                        **{f"step_{index}_duration": 8 for index in range(1, 9)},
                    }
                )

        self.assertEqual(result["behavior_segment"], "metadata_c")
        self.assertEqual(result["sequence_summary"]["encoder_available"], True)

    def test_behavior_model_service_defaults_to_model_metadata_filename(self):
        service = BehaviorModelService()

        self.assertEqual(service.metadata_path.name, "model_metadata.json")
        self.assertEqual(service.metrics_path.name, "model_comparison.json")


class BehaviorModelTrainingTests(TestCase):
    def test_split_uses_stratify_when_class_counts_are_safe(self):
        stratify_args = {}

        def fake_split(X, y, test_size, random_state, stratify):
            stratify_args["stratify"] = stratify
            return X[:4], X[4:], y[:4], y[4:]

        X = [[float(index)] for index in range(15)]
        y = [0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2]

        train_behavior_model_module._split_behavior_data(X, y, y, fake_split)

        self.assertEqual(stratify_args["stratify"], y)

    def test_split_disables_stratify_for_skewed_class_counts(self):
        stratify_args = {}

        def fake_split(X, y, test_size, random_state, stratify):
            stratify_args["stratify"] = stratify
            return X[:4], X[4:], y[:4], y[4:]

        X = [[0.0], [1.0], [2.0], [3.0], [4.0], [5.0]]
        y = [0, 0, 0, 0, 0, 1]

        train_behavior_model_module._split_behavior_data(X, y, y, fake_split)

        self.assertIsNone(stratify_args["stratify"])

    def test_metadata_uses_portable_relative_paths(self):
        schema = BehaviorDatasetSchema(feature_names=["a", "b"], labels=["no", "yes"])
        metadata = train_behavior_model_module._build_metadata(
            schema=schema,
            dataset_path=Path("c:/Users/admin/django_demo/bookstore-microservice/advisor-service/data/training/behavior_dataset.csv"),
            model_path=Path("c:/Users/admin/django_demo/bookstore-microservice/advisor-service/data/models/model_behavior.h5"),
            features_path=Path("c:/Users/admin/django_demo/bookstore-microservice/advisor-service/data/models/features.txt"),
            labels_path=Path("c:/Users/admin/django_demo/bookstore-microservice/advisor-service/data/models/labels.txt"),
            training_rows=6,
            test_rows=2,
            accuracy=0.75,
        )

        self.assertFalse(Path(metadata["dataset_path"]).is_absolute())
        self.assertFalse(Path(metadata["model_path"]).is_absolute())
        self.assertFalse(Path(metadata["features_path"]).is_absolute())
        self.assertFalse(Path(metadata["labels_path"]).is_absolute())


class GraphKnowledgeBaseTests(TestCase):
    def test_graph_loads_nodes_edges_adjacency_and_facts(self):
        graph = GraphKnowledgeBase("app/data/knowledge_graph")

        self.assertGreater(len(graph.nodes), 0)
        self.assertGreater(len(graph.edges), 0)
        self.assertGreater(len(graph.facts), 0)
        self.assertIn("segment:tech_reader", graph.nodes)
        self.assertIn("category:programming", graph.nodes)
        self.assertIsInstance(graph.nodes["segment:tech_reader"], GraphNode)
        self.assertIsInstance(graph.edges[0], GraphEdge)
        self.assertIn("category:programming", graph.neighbors("segment:tech_reader"))

        tech_reader_facts = graph.facts_for_node("segment:tech_reader")
        self.assertTrue(tech_reader_facts)
        self.assertTrue(all(fact.node_id == "segment:tech_reader" for fact in tech_reader_facts))
        self.assertTrue(any("programming" in fact.statement.lower() for fact in tech_reader_facts))

        adjacency = graph.edges_for_node("segment:tech_reader")
        self.assertTrue(adjacency["outgoing"])
        self.assertTrue(any(edge.target == "category:programming" for edge in adjacency["outgoing"]))

    def test_graph_loads_explicit_zero_weight_edges(self):
        with TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            (base_path / "nodes.json").write_text(
                json.dumps(
                    [
                        {"id": "node:a", "type": "segment", "label": "A"},
                        {"id": "node:b", "type": "category", "label": "B"},
                    ]
                ),
                encoding="utf-8",
            )
            (base_path / "edges.json").write_text(
                json.dumps(
                    [
                        {
                            "source": "node:a",
                            "target": "node:b",
                            "relation": "links_to",
                            "weight": 0,
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (base_path / "facts.json").write_text("[]", encoding="utf-8")

            graph = GraphKnowledgeBase(base_path)

        self.assertEqual(graph.edges[0].weight, 0.0)

    def test_graph_raises_when_files_are_missing(self):
        with TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir)
            (base_path / "nodes.json").write_text("[]", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                GraphKnowledgeBase(base_path)

    def test_graph_rejects_invalid_records(self):
        cases = [
            (
                "blank node id",
                {
                    "nodes.json": [
                        {"id": " ", "type": "segment", "label": "Blank"}
                    ],
                    "edges.json": [],
                    "facts.json": [],
                },
            ),
            (
                "duplicate node id",
                {
                    "nodes.json": [
                        {"id": "node:a", "type": "segment", "label": "A"},
                        {"id": "node:a", "type": "category", "label": "Duplicate"},
                    ],
                    "edges.json": [],
                    "facts.json": [],
                },
            ),
            (
                "dangling edge endpoint",
                {
                    "nodes.json": [
                        {"id": "node:a", "type": "segment", "label": "A"},
                        {"id": "node:b", "type": "category", "label": "B"},
                    ],
                    "edges.json": [
                        {
                            "source": "node:a",
                            "target": "node:missing",
                            "relation": "links_to",
                        }
                    ],
                    "facts.json": [],
                },
            ),
            (
                "malformed fact",
                {
                    "nodes.json": [
                        {"id": "node:a", "type": "segment", "label": "A"}
                    ],
                    "edges.json": [],
                    "facts.json": [
                        {
                            "id": "fact:a",
                            "node_id": " ",
                            "relation": "summary",
                            "statement": "Broken",
                        }
                    ],
                },
            ),
        ]

        for name, payloads in cases:
            with self.subTest(name=name):
                with TemporaryDirectory() as tmpdir:
                    base_path = Path(tmpdir)
                    for filename, payload in payloads.items():
                        (base_path / filename).write_text(json.dumps(payload), encoding="utf-8")

                    with self.assertRaises(ValueError):
                        GraphKnowledgeBase(base_path)

    def test_seed_graph_uses_all_declared_nodes(self):
        graph = GraphKnowledgeBase("app/data/knowledge_graph")
        referenced_nodes = {edge.source for edge in graph.edges} | {edge.target for edge in graph.edges} | {
            fact.node_id for fact in graph.facts
        }

        self.assertEqual(set(graph.nodes), referenced_nodes)


class GraphRetrieverTests(TestCase):
    def setUp(self):
        self.graph = GraphKnowledgeBase("app/data/knowledge_graph")
        self.retriever = GraphRetriever(self.graph)

    def _make_graph(self, nodes, edges, facts):
        class FakeGraph:
            def __init__(self, nodes, edges, facts):
                self.nodes = {node.id: node for node in nodes}
                self.edges = list(edges)
                self.facts = list(facts)

            def edges_for_node(self, node_id):
                outgoing = [edge for edge in self.edges if edge.source == node_id]
                incoming = [edge for edge in self.edges if edge.target == node_id]
                return {"outgoing": outgoing, "incoming": incoming}

            def facts_for_node(self, node_id):
                return [fact for fact in self.facts if fact.node_id == node_id]

        return FakeGraph(nodes, edges, facts)

    def test_graph_retriever_tokenization_drops_possessive_junk_tokens(self):
        self.assertIn("children", self.retriever._tokenize("children’s books"))
        self.assertNotIn("s", self.retriever._tokenize("children’s books"))

    def test_graph_retriever_ranks_facts_by_fact_specific_overlap(self):
        graph = self._make_graph(
            nodes=[
                GraphNode(
                    id="service:shipping",
                    type="service",
                    label="Shipping service",
                    metadata={},
                )
            ],
            edges=[],
            facts=[
                GraphFact(
                    id="fact-a-general",
                    node_id="service:shipping",
                    relation="summary",
                    statement="General policy overview for customers.",
                    metadata={"confidence": "high"},
                ),
                GraphFact(
                    id="fact-z-shipping",
                    node_id="service:shipping",
                    relation="summary",
                    statement="Shipping updates and tracking details help customers.",
                    metadata={"confidence": "high"},
                ),
            ],
        )

        result = GraphRetriever(graph).search(
            question="shipping updates",
            behavior_segment=None,
        )

        self.assertEqual(result["facts"][0]["id"], "fact-z-shipping")

    def test_graph_retriever_skips_policy_path_without_policy_keywords(self):
        graph = self._make_graph(
            nodes=[
                GraphNode(id="segment:window_shopper", type="segment", label="Window shopper", metadata={}),
                GraphNode(id="category:business", type="category", label="Business", metadata={}),
                GraphNode(id="policy:cancellation", type="policy", label="Cancellation policy", metadata={}),
            ],
            edges=[
                GraphEdge(
                    source="segment:window_shopper",
                    target="category:business",
                    relation="compares_options",
                    weight=0.7,
                    metadata={},
                ),
                GraphEdge(
                    source="category:business",
                    target="policy:cancellation",
                    relation="checks_before_buying",
                    weight=0.4,
                    metadata={},
                ),
            ],
            facts=[
                GraphFact(
                    id="fact-window-shopper",
                    node_id="segment:window_shopper",
                    relation="segment_summary",
                    statement="Window shoppers compare options but do not always buy.",
                    metadata={"confidence": "high"},
                )
            ],
        )

        result = GraphRetriever(graph).search(
            question="I need children's books.",
            behavior_segment="window_shopper",
        )

        self.assertFalse(
            any(
                path["nodes"] == ["segment:window_shopper", "category:business", "policy:cancellation"]
                for path in result["paths"]
            )
        )

    def test_graph_retriever_returns_segment_facts_and_direct_shipping_path(self):
        graph = self._make_graph(
            nodes=[
                GraphNode(id="segment:careful_researcher", type="segment", label="Careful researcher", metadata={}),
                GraphNode(id="service:shipping", type="service", label="Shipping service", metadata={}),
            ],
            edges=[
                GraphEdge(
                    source="segment:careful_researcher",
                    target="service:shipping",
                    relation="needs_reliable_delivery",
                    weight=0.6,
                    metadata={},
                )
            ],
            facts=[
                GraphFact(
                    id="fact-careful-researcher-shipping",
                    node_id="segment:careful_researcher",
                    relation="segment_summary",
                    statement="Careful researchers value reliable shipping updates.",
                    metadata={"confidence": "high"},
                ),
                GraphFact(
                    id="fact-careful-researcher-service",
                    node_id="service:shipping",
                    relation="service_summary",
                    statement="Shipping updates help careful researchers compare purchase timing.",
                    metadata={"confidence": "medium"},
                )
            ],
        )

        result = GraphRetriever(graph).search(
            question="I read novels and want reliable shipping updates for my books.",
            behavior_segment="careful_researcher",
        )

        self.assertTrue(result["facts"])
        self.assertTrue(result["paths"])

        fact_node_ids = [fact["node_id"] for fact in result["facts"]]
        self.assertIn("segment:careful_researcher", fact_node_ids)
        self.assertIn("service:shipping", fact_node_ids)
        self.assertTrue(any("shipping" in fact["statement"].lower() for fact in result["facts"]))
        self.assertTrue(
            any(
                path["nodes"] == ["segment:careful_researcher", "service:shipping"]
                for path in result["paths"]
            )
        )

    def test_graph_retriever_uses_category_relation_overlap_for_discount_hunter(self):
        graph = self._make_graph(
            nodes=[
                GraphNode(id="segment:discount_hunter", type="segment", label="Discount hunter", metadata={}),
                GraphNode(id="category:business", type="category", label="Business", metadata={}),
                GraphNode(id="policy:cancellation", type="policy", label="Cancellation policy", metadata={}),
            ],
            edges=[
                GraphEdge(
                    source="segment:discount_hunter",
                    target="category:business",
                    relation="optimizes_cost",
                    weight=0.88,
                    metadata={},
                ),
                GraphEdge(
                    source="category:business",
                    target="policy:cancellation",
                    relation="checks_before_buying",
                    weight=0.36,
                    metadata={},
                ),
            ],
            facts=[
                GraphFact(
                    id="fact-discount-hunter",
                    node_id="segment:discount_hunter",
                    relation="segment_summary",
                    statement="Discount hunters compare pricing and cancellation flexibility before buying.",
                    metadata={"confidence": "high"},
                ),
                GraphFact(
                    id="fact-discount-hunter-policy",
                    node_id="policy:cancellation",
                    relation="policy_summary",
                    statement="Cancellation flexibility matters to discount hunters.",
                    metadata={"confidence": "medium"},
                )
            ],
        )

        result = GraphRetriever(graph).search(
            question="I need discount details and flexible cancellation rules.",
            behavior_segment="discount_hunter",
        )

        fact_node_ids = [fact["node_id"] for fact in result["facts"]]
        self.assertIn("segment:discount_hunter", fact_node_ids)
        self.assertIn("policy:cancellation", fact_node_ids)
        self.assertTrue(
            any(node["id"] == "category:business" for node in result["matched_nodes"])
        )
        self.assertTrue(
            any(
                path["nodes"] == ["segment:discount_hunter", "category:business", "policy:cancellation"]
                for path in result["paths"]
            )
        )

    def test_graph_retriever_uses_neo4j_payload_when_available(self):
        class FakeNeo4jService:
            def __init__(self):
                self.calls = 0

            def query_graph_data(self):
                self.calls += 1
                return {
                    "nodes": [
                        {
                            "id": "segment:impulse_buyer",
                            "type": "segment",
                            "label": "Impulse buyer",
                            "metadata": {"description": "Impulse buyers discovered through Neo4j sync."},
                        },
                        {
                            "id": "category:programming",
                            "type": "category",
                            "label": "Programming",
                            "metadata": {},
                        },
                    ],
                    "edges": [
                        {
                            "source": "segment:impulse_buyer",
                            "target": "category:programming",
                            "relation": "prefers_fast_discovery",
                            "weight": 0.9,
                            "metadata": {},
                        }
                    ],
                    "facts": [
                        {
                            "id": "fact-impulse-buyer",
                            "node_id": "segment:impulse_buyer",
                            "relation": "segment_summary",
                            "statement": "Impulse buyers respond well to programming books.",
                            "metadata": {"confidence": "high"},
                        }
                    ],
                }

        retriever = GraphRetriever(self.graph, neo4j_service=FakeNeo4jService())
        result = retriever.search(
            question="What programming books suit an impulse buyer?",
            behavior_segment="impulse_buyer",
        )

        self.assertTrue(result["facts"])
        self.assertTrue(any(fact["id"] == "fact-impulse-buyer" for fact in result["facts"]))
        self.assertTrue(
            any(path["nodes"] == ["segment:impulse_buyer", "category:programming"] for path in result["paths"])
        )


class GraphExportBuilderTests(TestCase):
    def test_graph_export_builder_uses_rows_and_books(self):
        rows = [
            {
                "user_id": 1,
                "age_group": "18-25",
                "favorite_category": "technology",
                "price_sensitivity": "high",
                "membership_tier": "gold",
                "step_1_behavior": "search",
                "step_1_category": "technology",
                "step_1_price_band": "low",
                "step_1_duration": 12,
                "step_2_behavior": "view_detail",
                "step_2_category": "technology",
                "step_2_price_band": "mid",
                "step_2_duration": 10,
                "step_3_behavior": "add_to_cart",
                "step_3_category": "technology",
                "step_3_price_band": "mid",
                "step_3_duration": 8,
                "step_4_behavior": "checkout",
                "step_4_category": "technology",
                "step_4_price_band": "high",
                "step_4_duration": 6,
                "step_5_behavior": "review",
                "step_5_category": "technology",
                "step_5_price_band": "high",
                "step_5_duration": 5,
                "step_6_behavior": "view_home",
                "step_6_category": "technology",
                "step_6_price_band": "low",
                "step_6_duration": 4,
                "step_7_behavior": "search",
                "step_7_category": "technology",
                "step_7_price_band": "mid",
                "step_7_duration": 7,
                "step_8_behavior": "checkout",
                "step_8_category": "technology",
                "step_8_price_band": "high",
                "step_8_duration": 9,
                "label": "impulse_buyer",
            }
        ]
        books = [
            {"id": 101, "title": "Clean Code", "category": 3, "price": "29.99"},
            {"id": 102, "title": "Story Time", "category": 7, "price": "14.99"},
        ]

        payload = GraphKnowledgeBase.build_export_payload(rows, books)

        self.assertEqual(payload["metadata"]["row_count"], 1)
        self.assertEqual(payload["metadata"]["book_count"], 2)
        self.assertTrue(any(node["id"] == "segment:impulse_buyer" for node in payload["nodes"]))
        self.assertTrue(any(node["id"] == "book:101" for node in payload["nodes"]))
        self.assertTrue(any(node["id"] == "category:programming" for node in payload["nodes"]))
        self.assertTrue(
            any(
                edge["source"] == "segment:impulse_buyer" and edge["target"] == "category:programming"
                for edge in payload["edges"]
            )
        )
        self.assertTrue(
            any(edge["source"] == "book:101" and edge["target"] == "category:programming" for edge in payload["edges"])
        )
        self.assertTrue(
            any(
                fact["node_id"] == "segment:impulse_buyer"
                and "impulse buyers" in fact["statement"].lower()
                for fact in payload["facts"]
            )
        )

    def test_graph_export_builder_normalizes_string_category_ids(self):
        rows = [
            {
                "user_id": 7,
                "age_group": "26-35",
                "favorite_category": "category:9",
                "price_sensitivity": "medium",
                "membership_tier": "silver",
                "step_1_behavior": "search",
                "step_1_category": "9",
                "step_1_price_band": "mid",
                "step_1_duration": 11,
                "step_2_behavior": "view_detail",
                "step_2_category": "category:9",
                "step_2_price_band": "high",
                "step_2_duration": 10,
                "step_3_behavior": "checkout",
                "step_3_category": "9",
                "step_3_price_band": "high",
                "step_3_duration": 7,
                "step_4_behavior": "review",
                "step_4_category": "9",
                "step_4_price_band": "high",
                "step_4_duration": 5,
                "step_5_behavior": "view_home",
                "step_5_category": "category:category:9",
                "step_5_price_band": "mid",
                "step_5_duration": 4,
                "step_6_behavior": "search",
                "step_6_category": "9",
                "step_6_price_band": "mid",
                "step_6_duration": 6,
                "step_7_behavior": "view_detail",
                "step_7_category": "9",
                "step_7_price_band": "low",
                "step_7_duration": 8,
                "step_8_behavior": "checkout",
                "step_8_category": "category:9",
                "step_8_price_band": "high",
                "step_8_duration": 9,
                "label": "window_shopper",
            }
        ]
        books = [{"id": 201, "title": "Mystery Box", "category": "category:category:9", "price": "9.99"}]

        payload = GraphKnowledgeBase.build_export_payload(rows, books)

        category_ids = {node["id"] for node in payload["nodes"] if node["id"].startswith("category:")}
        self.assertIn("category:9", category_ids)
        self.assertFalse(any(node_id.startswith("category:category:") for node_id in category_ids))
        self.assertTrue(
            any(edge["source"] == "segment:window_shopper" and edge["target"] == "category:9" for edge in payload["edges"])
        )
        self.assertTrue(
            any(edge["source"] == "book:201" and edge["target"] == "category:9" for edge in payload["edges"])
        )


class Neo4jGraphServiceTests(TestCase):
    def test_neo4j_graph_service_reads_connection_details_and_syncs_payload(self):
        class FakeResult:
            def __init__(self, payload, tx):
                self.payload = payload
                self.tx = tx

            def single(self):
                if self.tx.closed:
                    raise RuntimeError("result consumed after transaction closed")
                return self.payload

        class FakeTransaction:
            def __init__(self):
                self.calls = []
                self.closed = False
                self.committed = False
                self.rolled_back = False

            def run(self, query, **params):
                self.calls.append((query, params))
                if query == Neo4jGraphService.NODE_SYNC_QUERY:
                    return FakeResult({"node_count": 1}, self)
                if query == Neo4jGraphService.EDGE_SYNC_QUERY:
                    return FakeResult({"edge_count": 1}, self)
                if query == Neo4jGraphService.FACT_SYNC_QUERY:
                    return FakeResult({"fact_count": 1}, self)
                return FakeResult({}, self)

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.closed = True
                return False

        class FakeSession:
            def __init__(self):
                self.tx = FakeTransaction()
                self.database = None

            def begin_transaction(self):
                return self.tx

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.tx.closed = True
                return False

        class FakeDriver:
            def __init__(self, session):
                self.session_obj = session

            def session(self, database=None):
                self.session_obj.database = database
                return self.session_obj

        session = FakeSession()
        payload = {
            "nodes": [
                {"id": "segment:impulse_buyer", "type": "segment", "label": "Impulse buyer", "metadata": {}}
            ],
            "edges": [
                {
                    "source": "segment:impulse_buyer",
                    "target": "category:programming",
                    "relation": "prefers_fast_discovery",
                    "weight": 1.0,
                    "metadata": {},
                }
            ],
            "facts": [
                {
                    "id": "fact-impulse-buyer-programming",
                    "node_id": "segment:impulse_buyer",
                    "relation": "segment_summary",
                    "statement": "Impulse buyers respond well to programming books.",
                    "metadata": {},
                }
            ],
        }

        with patch.dict(
            os.environ,
            {
                "NEO4J_URI": "bolt://example:7687",
                "NEO4J_USER": "neo4j",
                "NEO4J_PASSWORD": "secret",
                "NEO4J_DATABASE": "behavior_graph",
            },
            clear=False,
        ):
            service = Neo4jGraphService.from_env(driver=FakeDriver(session))

        self.assertEqual(service.uri, "bolt://example:7687")
        self.assertEqual(service.username, "neo4j")
        self.assertEqual(service.password, "secret")
        self.assertEqual(service.database, "behavior_graph")

        sync_result = service.sync_graph_data(payload)
        self.assertEqual(sync_result, {"synced": True, "node_count": 1, "edge_count": 1, "fact_count": 1})
        self.assertTrue(session.tx.calls)
        self.assertTrue(any("MERGE" in query for query, _ in session.tx.calls))
        self.assertTrue(session.tx.committed)
        self.assertFalse(session.tx.rolled_back)

        class QuerySession:
            def __init__(self):
                self.database = None
                self.calls = []

            def run(self, query, **params):
                self.calls.append((query, params))
                if "graph nodes" in query.lower():
                    return [
                        {
                            "id": "segment:impulse_buyer",
                            "type": "segment",
                            "label": "Impulse buyer",
                            "metadata": {},
                        },
                        {
                            "id": "category:programming",
                            "type": "category",
                            "label": "Programming",
                            "metadata": {},
                        },
                    ]
                if "graph edges" in query.lower():
                    return [
                        {
                            "source": "segment:impulse_buyer",
                            "target": "category:programming",
                            "relation": "prefers_fast_discovery",
                            "weight": 1.0,
                            "metadata": {},
                        }
                    ]
                if "graph facts" in query.lower():
                    return [
                        {
                            "id": "fact-impulse-buyer-programming",
                            "node_id": "segment:impulse_buyer",
                            "relation": "segment_summary",
                            "statement": "Impulse buyers respond well to programming books.",
                            "metadata": {},
                        }
                    ]
                return []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        query_service = Neo4jGraphService.from_env(driver=FakeDriver(QuerySession()))
        query_payload = query_service.query_graph_data()

        self.assertEqual(len(query_payload["nodes"]), 2)
        self.assertEqual(len(query_payload["edges"]), 1)
        self.assertEqual(len(query_payload["facts"]), 1)

    def test_neo4j_graph_service_rolls_back_when_later_write_fails(self):
        class FailingResult:
            def __init__(self, payload, tx):
                self.payload = payload
                self.tx = tx

            def single(self):
                if self.tx.closed:
                    raise RuntimeError("result consumed after transaction closed")
                return self.payload

        class FailingTransaction:
            def __init__(self):
                self.calls = []
                self.closed = False
                self.committed = False
                self.rolled_back = False

            def run(self, query, **params):
                self.calls.append((query, params))
                if query == Neo4jGraphService.NODE_SYNC_QUERY:
                    return FailingResult({"node_count": 1}, self)
                if query == Neo4jGraphService.EDGE_SYNC_QUERY:
                    raise RuntimeError("edge write failed")
                return FailingResult({}, self)

            def commit(self):
                self.committed = True

            def rollback(self):
                self.rolled_back = True

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.closed = True
                return False

        class FailingSession:
            def __init__(self):
                self.tx = FailingTransaction()

            def begin_transaction(self):
                return self.tx

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                self.tx.closed = True
                return False

        class FailingDriver:
            def __init__(self, session):
                self.session_obj = session

            def session(self, database=None):
                self.session_obj.database = database
                return self.session_obj

        session = FailingSession()
        service = Neo4jGraphService.from_env(driver=FailingDriver(session))

        with self.assertRaises(RuntimeError):
            service.sync_graph_data(
                {
                    "nodes": [
                        {"id": "segment:impulse_buyer", "type": "segment", "label": "Impulse buyer", "metadata": {}},
                        {"id": "category:programming", "type": "category", "label": "Programming", "metadata": {}},
                    ],
                    "edges": [
                        {
                            "source": "segment:impulse_buyer",
                            "target": "category:programming",
                            "relation": "prefers_fast_discovery",
                            "weight": 1.0,
                            "metadata": {},
                        }
                    ],
                    "facts": [],
                }
            )

        self.assertTrue(session.tx.calls)
        self.assertFalse(session.tx.committed)
        self.assertTrue(session.tx.rolled_back)


class SyncBehaviorGraphCommandTests(TestCase):
    def test_sync_behavior_graph_regenerates_artifacts_and_invokes_neo4j_sync(self):
        sync_behavior_graph_module = importlib.import_module("app.management.commands.sync_behavior_graph")

        class FakeUpstreamClient:
            def get_books(self):
                return [
                    {"id": 101, "title": "Clean Code", "category": 3, "price": "29.99"},
                    {"id": 102, "title": "Story Time", "category": 7, "price": "14.99"},
                ]

        class FakeNeo4jService:
            def __init__(self):
                self.synced_payloads = []

            def export_graph_data(self, rows, books):
                return GraphKnowledgeBase.build_export_payload(rows, books)

            def build_import_cypher(self):
                return "// fake import cypher"

            def sync_graph_data(self, payload):
                self.synced_payloads.append(payload)
                return {"synced": True, "node_count": len(payload["nodes"])}

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            fake_neo4j_service = FakeNeo4jService()
            with patch.object(sync_behavior_graph_module, "GRAPH_DATA_DIR", output_dir), patch.object(
                sync_behavior_graph_module, "UpstreamClient", return_value=FakeUpstreamClient()
            ), patch.object(
                sync_behavior_graph_module.Neo4jGraphService,
                "from_env",
                return_value=fake_neo4j_service,
            ):
                call_command("sync_behavior_graph", verbosity=0)

            self.assertTrue((output_dir / "nodes.json").exists())
            self.assertTrue((output_dir / "edges.json").exists())
            self.assertTrue((output_dir / "facts.json").exists())
            self.assertTrue((output_dir / "import.cypher").exists())
            self.assertTrue(fake_neo4j_service.synced_payloads)
            self.assertGreater(len(fake_neo4j_service.synced_payloads[0]["nodes"]), 0)

    def test_sync_behavior_graph_warns_and_keeps_artifacts_when_neo4j_sync_fails(self):
        sync_behavior_graph_module = importlib.import_module("app.management.commands.sync_behavior_graph")

        class FakeUpstreamClient:
            def get_books(self):
                return [{"id": 301, "title": "Practical Graphs", "category": 3, "price": "19.99"}]

        class FailingNeo4jService:
            def export_graph_data(self, rows, books):
                return GraphKnowledgeBase.build_export_payload(rows, books)

            def build_import_cypher(self):
                return "// failing import cypher"

            def sync_graph_data(self, payload):
                raise RuntimeError("neo4j unavailable")

        with TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            with patch.object(sync_behavior_graph_module, "GRAPH_DATA_DIR", output_dir), patch.object(
                sync_behavior_graph_module, "UpstreamClient", return_value=FakeUpstreamClient()
            ), patch.object(
                sync_behavior_graph_module.Neo4jGraphService,
                "from_env",
                return_value=FailingNeo4jService(),
            ):
                call_command("sync_behavior_graph", verbosity=0)

            self.assertTrue((output_dir / "nodes.json").exists())
            self.assertTrue((output_dir / "edges.json").exists())
            self.assertTrue((output_dir / "facts.json").exists())
            self.assertTrue((output_dir / "import.cypher").exists())


class TextRetrieverTests(TestCase):
    def setUp(self):
        self.retriever = TextRetriever(KnowledgeBaseService("app/data/knowledge_base"))

    def _make_text_retriever(self, documents):
        class FakeKBService:
            def __init__(self, documents):
                self._documents = documents

            def load_documents(self):
                return list(self._documents)

        return TextRetriever(FakeKBService(documents))

    def test_text_retriever_prefers_segment_advice_for_tech_reader_questions(self):
        docs = self.retriever.search(
            "What books should a tech reader buy?",
            behavior_segment="tech_reader",
            top_k=3,
        )

        self.assertGreaterEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "segment_tech_reader")
        self.assertEqual(docs[0]["target_segment"], "tech_reader")

    def test_text_retriever_prefers_shipping_faq_for_shipping_questions(self):
        docs = self.retriever.search(
            "How do shipping updates work for orders?",
            behavior_segment="casual_buyer",
            top_k=3,
        )

        self.assertGreaterEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "faq_shipping_policy")
        self.assertEqual(docs[0]["doc_type"], "faq")

    def test_text_retriever_uses_metadata_fallback_without_query_overlap(self):
        retriever = self._make_text_retriever(
            [
                {
                    "id": "segment_tech_reader",
                    "title": "Advice for technology readers",
                    "doc_type": "segment_advice",
                    "target_segment": "tech_reader",
                    "text": "Technology-oriented customers usually prefer programming, software engineering, data, and innovation books.",
                },
                {
                    "id": "faq_general_help",
                    "title": "General help",
                    "doc_type": "faq",
                    "target_segment": "all",
                    "text": "General support information for all customers.",
                },
            ]
        )

        docs = retriever.search("Need a gift for my engineering friend", behavior_segment="tech_reader", top_k=2)

        self.assertEqual(docs[0]["id"], "segment_tech_reader")
        self.assertGreater(docs[0]["score"], 0)
        self.assertTrue(any("segment" in reason for reason in docs[0]["reasons"]))

    def test_text_retriever_matches_tokenized_segment_labels(self):
        retriever = self._make_text_retriever(
            [
                {
                    "id": "segment_tech_reader",
                    "title": "Advice for technology readers",
                    "doc_type": "segment_advice",
                    "target_segment": "tech_reader",
                    "text": "Technology-oriented customers usually prefer programming, software engineering, data, and innovation books.",
                }
            ]
        )

        docs = retriever.search("What books fit a modern buyer?", behavior_segment="tech reader", top_k=1)

        self.assertEqual(docs[0]["id"], "segment_tech_reader")
        self.assertGreater(docs[0]["score"], 0)


class HybridRAGPipelineTests(TestCase):
    def setUp(self):
        graph = GraphKnowledgeBase("app/data/knowledge_graph")
        kb_service = KnowledgeBaseService("app/data/knowledge_base")
        self.pipeline = HybridRAGPipeline(
            GraphRetriever(graph),
            TextRetriever(kb_service),
        )

    def test_pipeline_returns_graph_facts_text_sources_and_context_blocks(self):
        result = self.pipeline.retrieve(
            question="Recommend books and explain shipping for a tech reader",
            behavior_segment="tech_reader",
            top_k=3,
        )

        self.assertIn("graph_facts", result)
        self.assertIn("graph_paths", result)
        self.assertIn("text_sources", result)
        self.assertIn("context_blocks", result)

        self.assertTrue(result["graph_facts"])
        self.assertTrue(result["text_sources"])
        self.assertTrue(result["context_blocks"])

        block_kinds = {block["kind"] for block in result["context_blocks"]}
        self.assertIn("graph_fact", block_kinds)
        self.assertIn("text_source", block_kinds)

        context_text = "\n".join(block.get("text", "") for block in result["context_blocks"])
        self.assertTrue(any(fact["statement"] in context_text for fact in result["graph_facts"]))
        self.assertTrue(any(source["text"] in context_text for source in result["text_sources"]))

    def test_pipeline_deduplicates_overlapping_evidence_and_orders_by_score(self):
        class FakeGraphRetriever:
            def search(self, question, behavior_segment=None, top_k=3):
                return {
                    "facts": [
                        {
                            "id": "fact-duplicate",
                            "node_id": "service:shipping",
                            "relation": "service_summary",
                            "statement": "Shipping guidance should explain delivery windows, tracking, and regional handling times.",
                            "score": 2.0,
                            "reasons": ["graph fact"],
                        }
                    ],
                    "paths": [
                        {
                            "nodes": ["segment:tech_reader", "service:shipping"],
                            "relations": ["relevant_to"],
                            "score": 4.0,
                            "reason": "graph path",
                        }
                    ],
                }

        class FakeTextRetriever:
            def search(self, question, behavior_segment=None, top_k=3):
                return [
                    {
                        "id": "doc-duplicate",
                        "title": "Shipping guidance",
                        "doc_type": "faq",
                        "target_segment": "all",
                        "text": "Shipping guidance should explain delivery windows, tracking, and regional handling times.",
                        "score": 1.5,
                        "reasons": ["text source"],
                    },
                    {
                        "id": "doc-higher",
                        "title": "Tech reader advice",
                        "doc_type": "segment_advice",
                        "target_segment": "tech_reader",
                        "text": "Technology readers usually prefer programming and data books.",
                        "score": 5.0,
                        "reasons": ["text source"],
                    },
                ]

        pipeline = HybridRAGPipeline(FakeGraphRetriever(), FakeTextRetriever())
        result = pipeline.retrieve("Recommend books", behavior_segment="tech_reader", top_k=3)

        self.assertEqual(len(result["context_blocks"]), 3)
        self.assertEqual([block["score"] for block in result["context_blocks"]], [5.0, 4.0, 2.0])
        self.assertEqual(result["context_blocks"][0]["kind"], "text_source")
        self.assertEqual(result["context_blocks"][1]["kind"], "graph_path")
        self.assertEqual(result["context_blocks"][2]["kind"], "graph_fact")
        duplicate_text = "Shipping guidance should explain delivery windows, tracking, and regional handling times."
        duplicate_blocks = [block for block in result["context_blocks"] if block.get("text") == duplicate_text]
        self.assertEqual(len(duplicate_blocks), 1)
        self.assertEqual(duplicate_blocks[0]["kind"], "graph_fact")

    def test_prompt_builder_accepts_hybrid_context_payload(self):
        from app.services.prompting import build_chat_prompt
        from app.services.prompting import RetrievalContext

        result = self.pipeline.retrieve(
            question="Recommend books and explain shipping for a tech reader",
            behavior_segment="tech_reader",
            top_k=2,
        )

        prompt = build_chat_prompt(
            question="Recommend books and explain shipping for a tech reader",
            behavior_segment="tech_reader",
            feature_summary="Predicted segment is tech_reader.",
            recommended_books=[{"title": "Clean Code", "price": "29.99"}],
            retrieval_context=RetrievalContext(
                graph_facts=result["graph_facts"],
                graph_paths=result["graph_paths"],
                text_sources=result["text_sources"],
                context_blocks=result["context_blocks"],
            ),
        )

        self.assertIn("Relevant context:", prompt)
        self.assertIn("Graph fact:", prompt)
        self.assertIn("Text source:", prompt)
        self.assertIn("Clean Code", prompt)
        self.assertNotIn("Graph path: Graph path", prompt)
        self.assertIn("Answer in natural Vietnamese.", prompt)

    def test_fallback_answer_uses_graph_context_when_available(self):
        answer = build_fallback_answer(
            question="How does shipping work?",
            behavior_segment="tech_reader",
            recommended_books=[{"title": "Clean Code"}],
            graph_facts=[{"statement": "Shipping updates matter for tech readers."}],
            graph_paths=[
                {
                    "nodes": ["segment:tech_reader", "service:shipping"],
                    "relations": ["relevant_to"],
                    "reason": "graph path to shipping guidance",
                }
            ],
        )

        self.assertIn("Shipping updates matter for tech readers.", answer)
        self.assertIn("graph path to shipping guidance", answer)

    def test_fallback_answer_is_localized_to_vietnamese_and_hides_internal_labels(self):
        answer = build_fallback_answer(
            question="hello",
            behavior_segment="loyal_reader",
            recommended_books=[{"title": "Gone Girl"}],
            graph_facts=[{"statement": "Loyal readers revisit familiar categories."}],
        )

        self.assertNotIn("behavior segment", answer.lower())
        self.assertNotIn("graph context", answer.lower())
        self.assertIn("goi y", answer.lower())
        self.assertIn("phu hop", answer.lower())


class PromptLocalizationTests(TestCase):
    def test_prompt_builder_instructs_the_llm_to_answer_in_vietnamese(self):
        prompt = build_chat_prompt(
            question="Xin chao",
            behavior_segment="loyal_reader",
            feature_summary="Khach hang co xu huong quay lai nhom sach quen thuoc.",
            recommended_books=[{"title": "Gone Girl", "price": "14.99"}],
        )

        self.assertIn("Vietnamese", prompt)
