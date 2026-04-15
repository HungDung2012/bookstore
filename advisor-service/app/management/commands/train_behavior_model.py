import json
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from app.services.behavior_dataset import BehaviorDatasetSchema
from app.services.behavior_model import build_behavior_model

APP_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = APP_DIR / "data" / "training" / "behavior_dataset.csv"
OUTPUT_DIR = APP_DIR / "data" / "models"


class Command(BaseCommand):
    help = "Train the deep learning behavior classifier."

    def handle(self, *args, **options):
        try:
            import pandas as pd
            from sklearn.model_selection import train_test_split
        except ImportError as exc:
            raise CommandError(
                "Training dependencies are not installed. Install pandas and scikit-learn to train the behavior model."
            ) from exc

        try:
            from tensorflow.keras.utils import to_categorical
        except ImportError as exc:
            raise CommandError(
                "TensorFlow is required to train the behavior model."
            ) from exc

        if not DATASET_PATH.exists():
            raise CommandError(f"Training dataset not found at {DATASET_PATH}")

        df = pd.read_csv(DATASET_PATH).fillna(0)
        if "user_id" in df.columns:
            df = df.drop(columns=["user_id"])
        if "label" not in df.columns:
            raise CommandError("Training dataset must include a label column.")

        records = df.to_dict(orient="records")
        schema = BehaviorDatasetSchema.from_rows(records)
        if not schema.feature_names or not schema.labels:
            raise CommandError("Training dataset must contain feature columns and labels.")

        X = np.asarray([schema.vectorize_features(row) for row in records], dtype="float32")
        y = np.asarray([schema.encode_label(row["label"]) for row in records], dtype="int32")
        y_one_hot = to_categorical(y, num_classes=len(schema.labels))

        X_train, X_test, y_train, y_test = train_test_split(
            X, y_one_hot, test_size=0.2, random_state=42
        )

        model = build_behavior_model(input_dim=X_train.shape[1], output_dim=y_one_hot.shape[1])
        model.fit(X_train, y_train, epochs=20, batch_size=8, verbose=0)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        model_path = OUTPUT_DIR / "model_behavior.h5"
        features_path = OUTPUT_DIR / "features.txt"
        labels_path = OUTPUT_DIR / "labels.txt"
        metadata_path = OUTPUT_DIR / "metadata.json"
        model.save(model_path)
        features_path.write_text("\n".join(schema.feature_names), encoding="utf-8")
        labels_path.write_text("\n".join(schema.labels), encoding="utf-8")
        _, accuracy = model.evaluate(X_test, y_test, verbose=0)
        metadata = {
            **schema.to_metadata(),
            "dataset_path": str(DATASET_PATH),
            "model_path": str(model_path),
            "features_path": str(features_path),
            "labels_path": str(labels_path),
            "training_rows": len(records),
            "test_rows": int(len(X_test)),
            "accuracy": float(accuracy),
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Model trained with accuracy={accuracy:.2f}"))
