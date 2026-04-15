from dataclasses import dataclass
from typing import Iterable


def _coerce_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class BehaviorDatasetSchema:
    feature_names: list[str]
    labels: list[str]

    @classmethod
    def from_rows(cls, rows: Iterable[dict]):
        rows = [row for row in rows if isinstance(row, dict)]
        feature_names = sorted(
            {
                key
                for row in rows
                for key in row.keys()
                if key != "label"
            }
        )
        labels = sorted(
            {
                str(row["label"]).strip()
                for row in rows
                if row.get("label") not in (None, "")
            }
        )
        return cls(feature_names=feature_names, labels=labels)

    def vectorize_features(self, features):
        feature_map = features if isinstance(features, dict) else {}
        return [_coerce_float(feature_map.get(name, 0.0)) for name in self.feature_names]

    def encode_label(self, label):
        label_value = str(label).strip()
        try:
            return self.labels.index(label_value)
        except ValueError as exc:
            raise ValueError(f"Unknown label: {label_value}") from exc

    def to_metadata(self):
        return {
            "feature_names": list(self.feature_names),
            "labels": list(self.labels),
            "feature_count": len(self.feature_names),
            "label_count": len(self.labels),
        }
