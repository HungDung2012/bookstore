import json
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from app.management.commands import train_behavior_model as train_behavior_model_module
from app.services.behavior_dataset import BehaviorDatasetSchema
from app.services.behavior_model import BehaviorModelService


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
            yield {"order_count": 1, "category_3_count": 2, "label": " tech_reader "}
            yield {"order_count": 2, "publisher_9_count": 1, "label": "casual_buyer"}

        schema = BehaviorDatasetSchema.from_rows(row_stream())

        self.assertEqual(
            schema.feature_names,
            ["category_3_count", "order_count", "publisher_9_count"],
        )
        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])

    def test_schema_normalizes_labels_with_whitespace(self):
        schema = BehaviorDatasetSchema.from_rows(
            [
                {"order_count": 1, "label": " tech_reader "},
                {"order_count": 2, "label": "casual_buyer"},
            ]
        )

        self.assertEqual(schema.labels, ["casual_buyer", "tech_reader"])
        self.assertEqual(schema.encode_label(" tech_reader "), 1)

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
