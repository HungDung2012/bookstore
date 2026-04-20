import json
import logging
from pathlib import Path

import numpy as np

from .behavior_dataset import (
    BehaviorSequenceSchema,
    SEQUENCE_PROFILE_FIELDS,
    SEQUENCE_STEP_COMPONENTS,
)

try:
    from tensorflow.keras.layers import Bidirectional, Dense, Dropout, Input, LSTM, SimpleRNN
    from tensorflow.keras.models import Sequential, load_model
except ImportError:
    Bidirectional = None
    Dense = None
    Dropout = None
    Input = None
    LSTM = None
    Sequential = None
    SimpleRNN = None

    def load_model(*args, **kwargs):
        raise RuntimeError("TensorFlow is not installed")


APP_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = APP_DIR / "data" / "models"
logger = logging.getLogger(__name__)

SEQUENCE_MODEL_PREFERENCE = ("bilstm", "lstm", "simple_rnn")
SEQUENCE_COMPONENTS = ("behavior", "category", "price_band")


def _coerce_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_metadata_list(values):
    if not isinstance(values, (list, tuple)):
        return None

    normalized = [str(value).strip() for value in values if str(value).strip()]
    return normalized or None


def _sorted_unique_values(rows, extractor):
    values = {
        str(value).strip()
        for row in rows
        for value in [extractor(row)]
        if str(value).strip()
    }
    return sorted(values)


def _build_sequence_encoder(rows, schema):
    profile_fields = [field for field in schema.profile_fields if field != "user_id"]
    step_count = len(schema.step_fields) // len(SEQUENCE_STEP_COMPONENTS)

    profile_vocabs = {
        field: _sorted_unique_values(rows, lambda row, name=field: row.get(name, ""))
        for field in profile_fields
    }
    step_vocabs = {}
    for component in SEQUENCE_COMPONENTS:
        step_vocabs[component] = sorted(
            {
                str(value).strip()
                for row in rows
                for value in [
                    row.get(f"step_{step_index}_{component}", "")
                    for step_index in range(1, step_count + 1)
                ]
                if str(value).strip()
            }
        )

    durations = [
        _coerce_float(row.get(f"step_{step_index}_duration"))
        for row in rows
        for step_index in range(1, step_count + 1)
    ]
    durations = [value for value in durations if value is not None]
    duration_min = min(durations) if durations else 0.0
    duration_max = max(durations) if durations else 1.0
    if duration_max <= duration_min:
        duration_max = duration_min + 1.0

    feature_dim = sum(len(vocab) for vocab in profile_vocabs.values())
    feature_dim += sum(len(vocab) for vocab in step_vocabs.values())
    feature_dim += 1

    return {
        "profile_fields": profile_fields,
        "step_components": list(SEQUENCE_COMPONENTS),
        "sequence_length": step_count,
        "feature_dim": feature_dim,
        "profile_vocabs": profile_vocabs,
        "step_vocabs": step_vocabs,
        "duration": {"min": float(duration_min), "max": float(duration_max)},
    }


def _one_hot_from_vocab(value, vocabulary):
    vector = np.zeros(len(vocabulary), dtype="float32")
    if not vocabulary:
        return vector

    value = str(value).strip()
    try:
        index = vocabulary.index(value)
    except ValueError:
        return vector

    vector[index] = 1.0
    return vector


def _normalize_duration(value, duration_min, duration_max):
    value = _coerce_float(value)
    if duration_max <= duration_min:
        return np.float32(0.0)
    normalized = (value - duration_min) / (duration_max - duration_min)
    return np.float32(np.clip(normalized, 0.0, 1.0))


def _encode_sequence_vector(row, encoder, step_index):
    vector_parts = []
    for field in encoder["profile_fields"]:
        vector_parts.append(_one_hot_from_vocab(row.get(field, ""), encoder["profile_vocabs"].get(field, [])))

    for component in SEQUENCE_COMPONENTS:
        field_name = f"step_{step_index}_{component}"
        vector_parts.append(_one_hot_from_vocab(row.get(field_name, ""), encoder["step_vocabs"].get(component, [])))

    duration = _normalize_duration(
        row.get(f"step_{step_index}_duration", 0.0),
        encoder["duration"]["min"],
        encoder["duration"]["max"],
    )
    vector_parts.append(np.asarray([duration], dtype="float32"))
    return np.concatenate(vector_parts).astype("float32", copy=False)


def encode_sequence_dataset(rows, schema=None, encoder=None):
    rows = [row for row in rows if isinstance(row, dict)]
    schema = schema or BehaviorSequenceSchema.from_rows(rows)
    encoder = encoder or _build_sequence_encoder(rows, schema)

    sample_count = len(rows)
    sequence_length = encoder["sequence_length"]
    feature_dim = encoder["feature_dim"]
    X = np.zeros((sample_count, sequence_length, feature_dim), dtype="float32")
    y_indices = np.asarray([schema.encode_label(row["label"]) for row in rows], dtype="int32")

    for row_index, row in enumerate(rows):
        for step_index in range(1, sequence_length + 1):
            X[row_index, step_index - 1, :] = _encode_sequence_vector(row, encoder, step_index)

    y = np.zeros((sample_count, len(schema.labels)), dtype="float32")
    if sample_count:
        y[np.arange(sample_count), y_indices] = 1.0

    return X, y, schema, encoder


def build_sequence_tensor(features, metadata):
    metadata = metadata or {}
    encoder = metadata.get("encoder")
    sequence_length = int(metadata.get("sequence_length") or 0)
    feature_dim = int(metadata.get("feature_dim") or 0)
    model_name = metadata.get("best_model_name") or metadata.get("model_name")

    if not isinstance(encoder, dict):
        return (
            np.zeros((1, sequence_length, feature_dim), dtype="float32"),
            {
                "model_name": model_name,
                "sequence_length": sequence_length,
                "feature_dim": feature_dim,
                "profile_fields": list(metadata.get("profile_fields") or []),
                "step_fields": list(metadata.get("step_fields") or []),
                "encoder_available": False,
            },
        )

    profile_fields = list(encoder.get("profile_fields") or [])
    sequence_length = int(encoder.get("sequence_length") or sequence_length or 0)
    feature_dim = int(encoder.get("feature_dim") or feature_dim or 0)
    profile_vocabs = encoder.get("profile_vocabs") or {}
    step_vocabs = encoder.get("step_vocabs") or {}
    duration = encoder.get("duration") or {"min": 0.0, "max": 1.0}

    computed_dim = sum(len(vocab) for vocab in profile_vocabs.values())
    computed_dim += sum(len(vocab) for vocab in step_vocabs.values())
    computed_dim += 1
    if feature_dim < computed_dim:
        feature_dim = computed_dim

    tensor = np.zeros((1, sequence_length, feature_dim), dtype="float32")
    step_components = list(encoder.get("step_components") or SEQUENCE_COMPONENTS)
    offset_map = []
    offset = 0
    for field in profile_fields:
        vocab = list(profile_vocabs.get(field) or [])
        offset_map.append(("profile", field, offset, vocab))
        offset += len(vocab)
    for component in step_components:
        vocab = list(step_vocabs.get(component) or [])
        offset_map.append(("step", component, offset, vocab))
        offset += len(vocab)
    duration_offset = offset

    for step_index in range(1, sequence_length + 1):
        row_vector = np.zeros(feature_dim, dtype="float32")
        vector_parts = []
        for kind, name, start, vocab in offset_map:
            if kind == "profile":
                vector = _one_hot_from_vocab(features.get(name, ""), vocab)
            else:
                vector = _one_hot_from_vocab(features.get(f"step_{step_index}_{name}", ""), vocab)
            row_vector[start : start + len(vocab)] = vector

        row_vector[duration_offset] = _normalize_duration(
            features.get(f"step_{step_index}_duration", 0.0),
            duration.get("min", 0.0),
            duration.get("max", 1.0),
        )
        tensor[0, step_index - 1, :] = row_vector

    summary = {
        "model_name": model_name,
        "sequence_length": sequence_length,
        "feature_dim": feature_dim,
        "profile_fields": profile_fields,
        "step_fields": list(metadata.get("step_fields") or []),
        "encoder_available": True,
    }
    return tensor, summary


def build_behavior_model(input_dim, output_dim):
    if any(component is None for component in (Sequential, Dense, Dropout, Input)):
        raise RuntimeError("TensorFlow is required to build the behavior model.")

    model = Sequential(
        [
            Input(shape=(input_dim,)),
            Dense(32, activation="relu"),
            Dropout(0.1),
            Dense(16, activation="relu"),
            Dense(output_dim, activation="softmax"),
        ]
    )
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model


def build_sequence_model(model_kind, timesteps, feature_dim, output_dim):
    if any(
        component is None
        for component in (Sequential, Dense, Dropout, Input, SimpleRNN, LSTM, Bidirectional)
    ):
        raise RuntimeError("TensorFlow is required to build the sequence behavior model.")

    layers = [Input(shape=(timesteps, feature_dim))]
    if model_kind == "simple_rnn":
        layers.extend([SimpleRNN(32), Dropout(0.1)])
    elif model_kind == "lstm":
        layers.extend([LSTM(32), Dropout(0.1)])
    elif model_kind == "bilstm":
        layers.extend([Bidirectional(LSTM(32)), Dropout(0.1)])
    else:
        raise ValueError(f"Unknown sequence model kind: {model_kind}")

    layers.extend([Dense(32, activation="relu"), Dense(output_dim, activation="softmax")])
    model = Sequential(layers)
    model.compile(optimizer="adam", loss="categorical_crossentropy", metrics=["accuracy"])
    return model


class BehaviorModelService:
    def __init__(
        self,
        model_path=MODEL_DIR / "model_best.keras",
        features_path=MODEL_DIR / "features.txt",
        labels_path=MODEL_DIR / "labels.txt",
        metadata_path=MODEL_DIR / "model_metadata.json",
        metrics_path=MODEL_DIR / "model_comparison.json",
    ):
        self.model_path = Path(model_path)
        self.features_path = Path(features_path)
        self.labels_path = Path(labels_path)
        self.metadata_path = Path(metadata_path)
        self.metrics_path = Path(metrics_path)
        self._model = None
        self._feature_names = None
        self._labels = None
        self._metadata = None

    def _metadata_describes_sequence_model(self, metadata):
        if not isinstance(metadata, dict):
            return False
        if isinstance(metadata.get("encoder"), dict):
            return True
        return bool(metadata.get("sequence_length") and metadata.get("feature_dim") and metadata.get("model_name"))

    def _read_artifact_lines(self, path, artifact_name):
        if not path.exists():
            logger.warning("Behavior model %s artifact missing at %s", artifact_name, path)
            return None

        try:
            lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except OSError as exc:
            logger.warning(
                "Failed to read behavior model %s artifact at %s: %s",
                artifact_name,
                path,
                exc,
            )
            return None

        if not lines:
            logger.warning("Behavior model %s artifact is empty at %s", artifact_name, path)
            return None

        return lines

    def _read_json_artifact(self, path, artifact_name):
        if not path.exists():
            logger.warning("Behavior model %s artifact missing at %s", artifact_name, path)
            return None

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning(
                "Failed to read behavior model %s artifact at %s: %s",
                artifact_name,
                path,
                exc,
            )
            return None

        if not isinstance(payload, dict):
            logger.warning("Behavior model %s artifact must be a JSON object at %s", artifact_name, path)
            return None

        return payload

    def _normalize_metadata_list(self, values):
        return _normalize_metadata_list(values)

    def _load_metadata(self):
        if self._metadata is None:
            self._metadata = self._read_json_artifact(self.metadata_path, "metadata")
            if self._metadata is None and self.metadata_path.name == "model_metadata.json":
                legacy_path = self.metadata_path.with_name("metadata.json")
                self._metadata = self._read_json_artifact(legacy_path, "metadata")
        return self._metadata

    def _load_artifact_list(self, metadata_key, artifact_path, artifact_name):
        metadata = self._load_metadata() or {}
        metadata_values = None
        if isinstance(metadata, dict):
            metadata_values = self._normalize_metadata_list(metadata.get(metadata_key))

        artifact_values = self._read_artifact_lines(artifact_path, artifact_name)
        if metadata_values is None:
            return artifact_values
        if artifact_values is None:
            return metadata_values
        if metadata_values != artifact_values:
            logger.warning(
                "Behavior model %s metadata at %s is inconsistent with %s artifact at %s; using artifact file instead",
                metadata_key,
                self.metadata_path,
                artifact_name,
                artifact_path,
            )
            return artifact_values
        return metadata_values

    def _load_labels(self):
        if self._labels is None:
            metadata = self._load_metadata() or {}
            if self._metadata_describes_sequence_model(metadata):
                self._labels = self._normalize_metadata_list(metadata.get("labels") or metadata.get("label_family"))
                if self._labels is None:
                    self._labels = self._load_artifact_list("labels", self.labels_path, "labels")
            else:
                artifact_labels = self._load_artifact_list("labels", self.labels_path, "labels")
                if artifact_labels is not None:
                    self._labels = artifact_labels
                else:
                    self._labels = self._normalize_metadata_list(metadata.get("labels") or metadata.get("label_family"))
        return self._labels

    def _load_feature_names(self):
        if self._feature_names is None:
            metadata = self._load_metadata() or {}
            if self._metadata_describes_sequence_model(metadata):
                self._feature_names = self._normalize_metadata_list(metadata.get("feature_names"))
                if self._feature_names is None:
                    self._feature_names = self._load_artifact_list("feature_names", self.features_path, "features")
            else:
                artifact_features = self._load_artifact_list("feature_names", self.features_path, "features")
                if artifact_features is not None:
                    self._feature_names = artifact_features
                else:
                    self._feature_names = self._normalize_metadata_list(metadata.get("feature_names"))
        return self._feature_names

    def _load_model(self):
        if self._model is None:
            if not self.model_path.exists():
                logger.warning("Behavior model artifact missing at %s", self.model_path)
                return None
            try:
                self._model = load_model(self.model_path)
            except Exception as exc:
                logger.warning("Failed to load behavior model from %s: %s", self.model_path, exc)
                self._model = None
        return self._model

    def _load_model_name(self):
        metadata = self._load_metadata() or {}
        return metadata.get("best_model_name") or metadata.get("model_name") or self.model_path.stem

    def _vectorize(self, features):
        feature_names = self._load_feature_names()
        if feature_names is None:
            return None
        return np.array([[float(features.get(name, 0.0)) for name in feature_names]], dtype="float32")

    def _encode_input(self, features):
        metadata = self._load_metadata() or {}
        if metadata.get("encoder") or metadata.get("sequence_length") or metadata.get("feature_dim"):
            return build_sequence_tensor(features, metadata)
        vector = self._vectorize(features)
        summary = {
            "model_name": self._load_model_name(),
            "sequence_length": 1,
            "feature_dim": 0 if vector is None else int(vector.shape[1]),
            "profile_fields": [],
            "step_fields": [],
            "encoder_available": False,
        }
        return vector, summary

    def predict(self, features):
        model = self._load_model()
        labels = self._load_labels()
        tensor, sequence_summary = self._encode_input(features)
        model_name = sequence_summary.get("model_name") or self._load_model_name()

        if model is None or labels is None or tensor is None:
            return {
                "behavior_segment": "casual_buyer",
                "probabilities": {},
                "model_name": model_name,
                "sequence_summary": sequence_summary,
            }

        probabilities = model.predict(tensor, verbose=0)[0]
        if len(probabilities) != len(labels):
            logger.warning(
                "Behavior model probability count %s does not match label count %s",
                len(probabilities),
                len(labels),
            )
            return {
                "behavior_segment": "casual_buyer",
                "probabilities": {},
                "model_name": model_name,
                "sequence_summary": sequence_summary,
            }

        best_index = int(np.argmax(probabilities))
        return {
            "behavior_segment": labels[best_index],
            "probabilities": {
                label: float(prob)
                for label, prob in zip(labels, probabilities)
            },
            "model_name": model_name,
            "sequence_summary": sequence_summary,
        }
