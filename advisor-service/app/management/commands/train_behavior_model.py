from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

APP_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = APP_DIR / "data" / "training" / "behavior_dataset.csv"
OUTPUT_DIR = APP_DIR / "data" / "models"


class Command(BaseCommand):
    help = "Train the deep learning behavior classifier."

    def handle(self, *args, **options):
        try:
            import pandas as pd
            from sklearn.model_selection import train_test_split
            from sklearn.preprocessing import LabelEncoder
        except ImportError as exc:
            raise CommandError(
                "Training dependencies are not installed. Install pandas and scikit-learn to train the behavior model."
            ) from exc

        try:
            from tensorflow.keras import Sequential
            from tensorflow.keras.layers import Dense, Dropout
            from tensorflow.keras.utils import to_categorical
        except ImportError as exc:
            raise CommandError(
                "TensorFlow is required to train the behavior model."
            ) from exc

        if not DATASET_PATH.exists():
            raise CommandError(f"Training dataset not found at {DATASET_PATH}")

        df = pd.read_csv(DATASET_PATH).fillna(0)

        y = df.pop("label")
        if "user_id" in df.columns:
            df.pop("user_id")

        encoder = LabelEncoder()
        y_encoded = encoder.fit_transform(y)
        y_one_hot = to_categorical(y_encoded)

        X_train, X_test, y_train, y_test = train_test_split(
            df.values, y_one_hot, test_size=0.2, random_state=42
        )

        model = Sequential(
            [
                Dense(32, activation="relu", input_shape=(X_train.shape[1],)),
                Dropout(0.2),
                Dense(16, activation="relu"),
                Dense(y_one_hot.shape[1], activation="softmax"),
            ]
        )
        model.compile(
            optimizer="adam",
            loss="categorical_crossentropy",
            metrics=["accuracy"],
        )
        model.fit(X_train, y_train, epochs=20, batch_size=8, verbose=0)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        model.save(OUTPUT_DIR / "model_behavior.h5")
        (OUTPUT_DIR / "labels.txt").write_text("\n".join(encoder.classes_), encoding="utf-8")
        (OUTPUT_DIR / "features.txt").write_text("\n".join(df.columns.tolist()), encoding="utf-8")
        _, accuracy = model.evaluate(X_test, y_test, verbose=0)
        self.stdout.write(self.style.SUCCESS(f"Model trained with accuracy={accuracy:.2f}"))
