import json
import importlib
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.management.commands import train_behavior_model as train_behavior_model_module
from app.services.behavior_dataset import BehaviorDatasetSchema
from app.services.behavior_model import BehaviorModelService
from app.services.graph_kb import GraphEdge, GraphFact, GraphKnowledgeBase, GraphNode
from app.services.graph_retriever import GraphRetriever
from app.services.knowledge_base import KnowledgeBaseService
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


class PrepareBehaviorDataTests(TestCase):
    def test_prepare_behavior_data_writes_schema_aligned_rows_with_labels(self):
        from app.management.commands import prepare_behavior_data as prepare_behavior_data_module

        class FakeClient:
            def get_books(self):
                return [{"id": 1, "category": 3, "publisher": 9}]

            def get_user(self, user_id):
                return {"id": user_id}

            def get_orders(self, user_id):
                return [
                    {
                        "total_amount": 20,
                        "items": [{"book_id": 1, "quantity": 2}],
                    }
                ]

            def get_reviews(self, user_id):
                return [{"rating": 5}]

            def get_cart(self, user_id):
                return [{"book_id": 1}]

        with TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "behavior_dataset.csv"
            with patch.object(prepare_behavior_data_module, "OUTPUT_PATH", output_path), patch.object(
                prepare_behavior_data_module, "UpstreamClient", return_value=FakeClient()
            ):
                prepare_behavior_data_module.Command().handle()

            with output_path.open("r", encoding="utf-8", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                rows = list(reader)
                fieldnames = reader.fieldnames

        self.assertIsNotNone(fieldnames)
        self.assertNotIn("user_id", fieldnames)
        self.assertEqual(fieldnames, BehaviorDatasetSchema.from_rows(rows).export_fieldnames)
        self.assertEqual(len(rows), 20)
        self.assertTrue(all(row["label"] == "tech_reader" for row in rows))
        self.assertEqual(rows[0]["category_3_count"], "2.0")


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
        result = self.retriever.search(
            question="I need children's books.",
            behavior_segment="family_reader",
        )

        self.assertFalse(
            any(
                path["nodes"] == ["segment:family_reader", "category:children", "policy:cancellation"]
                for path in result["paths"]
            )
        )

    def test_graph_retriever_returns_segment_facts_and_direct_shipping_path(self):
        result = self.retriever.search(
            question="I read novels and want reliable shipping updates for my books.",
            behavior_segment="literature_reader",
        )

        self.assertTrue(result["facts"])
        self.assertTrue(result["paths"])

        fact_node_ids = [fact["node_id"] for fact in result["facts"]]
        self.assertIn("segment:literature_reader", fact_node_ids)
        self.assertIn("service:shipping", fact_node_ids)
        self.assertTrue(any("shipping" in fact["statement"].lower() for fact in result["facts"]))
        self.assertTrue(
            any(
                path["nodes"] == ["segment:literature_reader", "service:shipping"]
                for path in result["paths"]
            )
        )

    def test_graph_retriever_uses_category_relation_overlap_for_family_reader(self):
        result = self.retriever.search(
            question="I need children's books and flexible cancellation rules.",
            behavior_segment="family_reader",
        )

        fact_node_ids = [fact["node_id"] for fact in result["facts"]]
        self.assertIn("segment:family_reader", fact_node_ids)
        self.assertIn("policy:cancellation", fact_node_ids)
        self.assertTrue(
            any(node["id"] == "category:children" for node in result["matched_nodes"])
        )
        self.assertTrue(
            any(
                path["nodes"] == ["segment:family_reader", "category:children", "policy:cancellation"]
                for path in result["paths"]
            )
        )


class TextRetrieverTests(TestCase):
    def setUp(self):
        self.retriever = TextRetriever(KnowledgeBaseService("app/data/knowledge_base"))

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
