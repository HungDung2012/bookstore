import json
import logging
from pathlib import Path

import numpy as np

try:
    from tensorflow.keras.layers import Dense, Dropout, Input
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.models import load_model
except ImportError:
    Dense = None
    Dropout = None
    Input = None
    Sequential = None

    def load_model(*args, **kwargs):
        raise RuntimeError("TensorFlow is not installed")


APP_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = APP_DIR / "data" / "models"
logger = logging.getLogger(__name__)


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


class BehaviorModelService:
    def __init__(
        self,
        model_path=MODEL_DIR / "model_behavior.h5",
        features_path=MODEL_DIR / "features.txt",
        labels_path=MODEL_DIR / "labels.txt",
        metadata_path=MODEL_DIR / "metadata.json",
    ):
        self.model_path = Path(model_path)
        self.features_path = Path(features_path)
        self.labels_path = Path(labels_path)
        self.metadata_path = Path(metadata_path)
        self._model = None
        self._feature_names = None
        self._labels = None
        self._metadata = None

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

    def _load_metadata(self):
        if self._metadata is None:
            self._metadata = self._read_json_artifact(self.metadata_path, "metadata")
        return self._metadata

    def _load_labels(self):
        if self._labels is None:
            metadata = self._load_metadata() or {}
            labels = metadata.get("labels") if isinstance(metadata, dict) else None
            if labels:
                self._labels = [str(label).strip() for label in labels if str(label).strip()]
            if self._labels is None:
                self._labels = self._read_artifact_lines(self.labels_path, "labels")
        return self._labels

    def _load_feature_names(self):
        if self._feature_names is None:
            metadata = self._load_metadata() or {}
            feature_names = metadata.get("feature_names") if isinstance(metadata, dict) else None
            if feature_names:
                self._feature_names = [str(name).strip() for name in feature_names if str(name).strip()]
            if self._feature_names is None:
                self._feature_names = self._read_artifact_lines(self.features_path, "features")
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

    def _vectorize(self, features):
        feature_names = self._load_feature_names()
        if feature_names is None:
            return None
        return np.array([[float(features.get(name, 0.0)) for name in feature_names]])

    def predict(self, features):
        model = self._load_model()
        labels = self._load_labels()
        vector = self._vectorize(features)
        if model is None or labels is None or vector is None:
            return {"behavior_segment": "casual_buyer", "probabilities": {}}

        probabilities = model.predict(vector, verbose=0)[0]
        if len(probabilities) != len(labels):
            logger.warning(
                "Behavior model probability count %s does not match label count %s",
                len(probabilities),
                len(labels),
            )
            return {"behavior_segment": "casual_buyer", "probabilities": {}}

        best_index = int(np.argmax(probabilities))
        return {
            "behavior_segment": labels[best_index],
            "probabilities": {
                label: float(prob)
                for label, prob in zip(labels, probabilities)
            },
        }
