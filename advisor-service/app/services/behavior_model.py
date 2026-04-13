from pathlib import Path

import numpy as np

try:
    from tensorflow.keras.models import load_model
except ImportError:
    def load_model(*args, **kwargs):
        raise RuntimeError("TensorFlow is not installed")


class BehaviorModelService:
    labels = [
        "tech_reader",
        "literature_reader",
        "family_reader",
        "bargain_hunter",
        "casual_buyer",
    ]

    def __init__(
        self,
        model_path="app/data/models/model_behavior.h5",
        features_path="app/data/models/features.txt",
    ):
        self.model_path = Path(model_path)
        self.features_path = Path(features_path)
        self._model = None

    def _load_model(self):
        if self._model is None:
            try:
                self._model = load_model(self.model_path)
            except Exception:
                self._model = None
        return self._model

    def _vectorize(self, features):
        if self.features_path.exists():
            feature_names = self.features_path.read_text(encoding="utf-8").splitlines()
        else:
            feature_names = list(features.keys())
        return np.array([[float(features.get(name, 0.0)) for name in feature_names]])

    def predict(self, features):
        model = self._load_model()
        if model is None:
            return {"behavior_segment": "casual_buyer", "probabilities": {}}

        probabilities = model.predict(self._vectorize(features), verbose=0)[0]
        best_index = int(np.argmax(probabilities))
        return {
            "behavior_segment": self.labels[best_index],
            "probabilities": {
                label: float(prob)
                for label, prob in zip(self.labels, probabilities)
            },
        }
