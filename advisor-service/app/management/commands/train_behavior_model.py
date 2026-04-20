import json
import logging
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand, CommandError
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score, precision_score, recall_score

from app.services.behavior_dataset import BehaviorDatasetSchema, BehaviorSequenceSchema
from app.services.behavior_model import (
    SEQUENCE_MODEL_PREFERENCE,
    SEQUENCE_COMPONENTS,
    build_sequence_model,
    encode_sequence_dataset,
)

APP_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = APP_DIR / "data" / "training" / "data_user500.csv"
OUTPUT_DIR = APP_DIR / "data" / "models"
PLOTS_DIR = OUTPUT_DIR / "plots"
MODEL_FILENAMES = {
    "simple_rnn": "model_simple_rnn.keras",
    "lstm": "model_lstm.keras",
    "bilstm": "model_bilstm.keras",
}
BEST_MODEL_FILENAME = "model_best.keras"
COMPARISON_FILENAME = "model_comparison.json"
METADATA_FILENAME = "model_metadata.json"
EPOCHS = 8
BATCH_SIZE = 16
TEST_SIZE = 0.2
VALIDATION_SIZE = 0.2
RANDOM_STATE = 42
logger = logging.getLogger(__name__)


def _portable_path(path):
    path = Path(path)
    try:
        return path.relative_to(APP_DIR).as_posix()
    except ValueError:
        return path.name


def _should_stratify_split(labels, test_size=0.2):
    unique_labels, counts = np.unique(labels, return_counts=True)
    if len(unique_labels) < 2:
        raise CommandError("Training dataset must contain at least two behavior classes.")
    if len(labels) < 2:
        raise CommandError("Training dataset must contain at least two training rows.")

    test_count = int(np.ceil(test_size * len(labels)))
    train_count = len(labels) - test_count
    if counts.min() < 2:
        logger.warning(
            "Behavior dataset class counts are too small for a stratified split; using an unstratified split instead."
        )
        return None
    if test_count < len(unique_labels) or train_count < len(unique_labels):
        logger.warning(
            "Behavior dataset is too small for a stratified split; using an unstratified split instead."
        )
        return None
    return labels


def _split_behavior_data(X, y, labels, splitter, test_size=0.2, random_state=42):
    stratify = _should_stratify_split(labels, test_size=test_size)
    return splitter(X, y, test_size=test_size, random_state=random_state, stratify=stratify)


def _split_sequence_rows(rows, validation_size=VALIDATION_SIZE, test_size=TEST_SIZE, random_state=RANDOM_STATE):
    try:
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise CommandError(
            "Training dependencies are not installed. Install pandas and scikit-learn to train the behavior model."
        ) from exc

    if not rows:
        raise CommandError("Training dataset is empty.")

    labels = np.asarray([str(row.get("label", "")).strip() for row in rows], dtype=object)
    if len(rows) < 3:
        raise CommandError("Training dataset must contain at least three rows.")

    train_rows, test_rows = train_test_split(
        rows,
        test_size=test_size,
        random_state=random_state,
        stratify=_should_stratify_split(labels, test_size=test_size),
    )
    train_labels = np.asarray([str(row.get("label", "")).strip() for row in train_rows], dtype=object)
    validation_fraction = validation_size / max(1.0 - test_size, 1e-9)
    train_rows, validation_rows = train_test_split(
        train_rows,
        test_size=validation_fraction,
        random_state=random_state,
        stratify=_should_stratify_split(train_labels, test_size=validation_fraction),
    )
    return train_rows, validation_rows, test_rows


def _build_metadata(schema, dataset_path, model_path, features_path, labels_path, training_rows, test_rows, accuracy):
    return {
        **schema.to_metadata(),
        "dataset_path": _portable_path(dataset_path),
        "model_path": _portable_path(model_path),
        "features_path": _portable_path(features_path),
        "labels_path": _portable_path(labels_path),
        "training_rows": training_rows,
        "test_rows": test_rows,
        "accuracy": float(accuracy),
    }


def _select_best_model(model_metrics):
    if not model_metrics:
        raise CommandError("No model metrics were produced.")

    preference = {name: index for index, name in enumerate(SEQUENCE_MODEL_PREFERENCE[::-1])}

    def sort_key(item):
        name, metrics = item
        return (
            float(metrics.get("f1_macro", 0.0)),
            float(metrics.get("accuracy", 0.0)),
            preference.get(name, -1),
        )

    return max(model_metrics.items(), key=sort_key)[0]


def _select_best_model_from_validation(validation_metrics, test_metrics=None):
    del test_metrics
    return _select_best_model(validation_metrics)


def _rank_model_metrics(model_metrics):
    preference = {name: index for index, name in enumerate(SEQUENCE_MODEL_PREFERENCE[::-1])}
    ranked = sorted(
        (
            {
                "model_name": name,
                **metrics,
            }
            for name, metrics in model_metrics.items()
        ),
        key=lambda item: (
            float(item.get("f1_macro", 0.0)),
            float(item.get("accuracy", 0.0)),
            preference.get(item["model_name"], -1),
        ),
        reverse=True,
    )
    return ranked


def _load_sequence_rows(dataset_path):
    try:
        import pandas as pd
    except ImportError as exc:
        raise CommandError(
            "Training dependencies are not installed. Install pandas and scikit-learn to train the behavior model."
        ) from exc

    if not dataset_path.exists():
        raise CommandError(f"Training dataset not found at {dataset_path}")

    df = pd.read_csv(dataset_path).fillna("")
    if "label" not in df.columns:
        raise CommandError("Training dataset must include a label column.")

    rows = df.to_dict(orient="records")
    schema = BehaviorSequenceSchema.from_rows(rows)
    return rows, schema


def _encode_rows_with_encoder(rows, schema=None, encoder=None):
    schema = schema or BehaviorSequenceSchema.from_rows(rows)
    X, y, schema, encoder = encode_sequence_dataset(rows, schema=schema, encoder=encoder)
    return X, y, schema, encoder


def _fit_sequence_encoder(rows, schema=None):
    _, _, schema, encoder = _encode_rows_with_encoder(rows, schema=schema)
    return encoder, schema


def _build_sequence_dataset_metadata(schema, encoder):
    return {
        **schema.to_metadata(),
        "feature_names": _sequence_feature_names_from_encoder(encoder),
        "labels": list(schema.labels),
        "profile_fields": [field for field in schema.profile_fields if field != "user_id"],
        "ignored_fields": ["user_id"],
        "sequence_length": encoder["sequence_length"],
        "feature_dim": encoder["feature_dim"],
        "encoder": encoder,
    }


def _sequence_feature_names_from_encoder(encoder):
    feature_names = list(encoder.get("profile_fields") or [])
    feature_names.extend(f"step_{component}" for component in encoder.get("step_components") or SEQUENCE_COMPONENTS)
    return feature_names


def _build_model_artifact_payload(
    model_name,
    labels,
    confusion_matrix,
    classification_report,
    history=None,
    metrics=None,
    validation_metrics=None,
    test_metrics=None,
):
    validation_metrics = validation_metrics or metrics or {}
    test_metrics = test_metrics or {}
    payload = {
        "model_name": model_name,
        "labels": list(labels),
        "metrics": dict(validation_metrics),
        "validation_metrics": dict(validation_metrics),
        "test_metrics": dict(test_metrics),
        "confusion_matrix": confusion_matrix,
        "classification_report": classification_report,
    }
    if history is not None:
        payload["training_history"] = history
    return payload


def _build_comparison_payload(
    dataset_path,
    best_model_name,
    model_metrics=None,
    validation_metrics=None,
    test_metrics=None,
):
    model_metrics = model_metrics or validation_metrics or {}
    test_metrics = test_metrics or {}
    return {
        "dataset_path": _portable_path(dataset_path),
        "best_model_name": best_model_name,
        "preference_order": list(SEQUENCE_MODEL_PREFERENCE),
        "models": {
            name: {
                **{
                    key: value
                    for key, value in metrics.items()
                    if key not in {"validation_metrics", "test_metrics"}
                },
                "validation_metrics": dict(metrics.get("validation_metrics", {})),
                "test_metrics": dict(metrics.get("test_metrics", test_metrics.get(name, {}))),
                "model_name": name,
            }
            for name, metrics in model_metrics.items()
        },
        "ranking": _rank_model_metrics(model_metrics),
    }


def _build_sequence_metadata(
    schema,
    dataset_path,
    model_paths,
    comparison_path,
    evaluation_paths,
    plot_paths,
    best_model_name,
    training_rows,
    validation_rows,
    test_rows,
    encoder,
):
    best_model_path = model_paths[best_model_name]
    return {
        **schema.to_metadata(),
        "feature_names": [*(field for field in schema.profile_fields if field != "user_id"), *SEQUENCE_COMPONENTS],
        "dataset_path": _portable_path(dataset_path),
        "model_path": _portable_path(best_model_path),
        "comparison_path": _portable_path(comparison_path),
        "best_model_name": best_model_name,
        "model_name": best_model_name,
        "labels": list(schema.labels),
        "profile_fields": [field for field in schema.profile_fields if field != "user_id"],
        "ignored_fields": ["user_id"],
        "sequence_length": encoder["sequence_length"],
        "feature_dim": encoder["feature_dim"],
        "encoder": encoder,
        "candidate_model_paths": {name: _portable_path(path) for name, path in model_paths.items()},
        "evaluation_paths": {name: _portable_path(path) for name, path in evaluation_paths.items()},
        "plot_paths": {name: _portable_path(path) for name, path in plot_paths.items()},
        "training_rows": training_rows,
        "validation_rows": validation_rows,
        "test_rows": test_rows,
    }


def _build_metrics_payload(dataset_path, best_model_name, model_metrics):
    return {
        "dataset_path": _portable_path(dataset_path),
        "best_model_name": best_model_name,
        "preference_order": list(SEQUENCE_MODEL_PREFERENCE),
        "models": {
            name: {
                **{
                    key: value
                    for key, value in metrics.items()
                    if key not in {"validation_metrics", "test_metrics"}
                },
                "validation_metrics": dict(metrics.get("validation_metrics", {})),
                "test_metrics": dict(metrics.get("test_metrics", {})),
                "model_name": name,
            }
            for name, metrics in model_metrics.items()
        },
        "ranking": _rank_model_metrics(model_metrics),
    }


def _save_training_history_plot(history, path, model_name):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise CommandError("Matplotlib is required to write behavior model plots.") from exc

    history_payload = getattr(history, "history", {}) or {}
    epochs = range(1, len(history_payload.get("loss", [])) + 1)

    plt.figure(figsize=(8, 4.5))
    if history_payload.get("loss"):
        plt.plot(epochs, history_payload["loss"], label="loss")
    if history_payload.get("accuracy"):
        plt.plot(epochs, history_payload["accuracy"], label="accuracy")
    if history_payload.get("val_loss"):
        plt.plot(epochs, history_payload["val_loss"], label="val_loss")
    if history_payload.get("val_accuracy"):
        plt.plot(epochs, history_payload["val_accuracy"], label="val_accuracy")
    plt.title(f"Training history: {model_name}")
    plt.xlabel("Epoch")
    plt.ylabel("Metric value")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def _save_comparison_plot(model_metrics, path):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise CommandError("Matplotlib is required to write behavior model plots.") from exc

    metric_names = ["accuracy", "precision_macro", "recall_macro", "f1_macro"]
    model_names = list(model_metrics)
    x = np.arange(len(model_names))
    width = 0.18

    plt.figure(figsize=(10, 5))
    for index, metric_name in enumerate(metric_names):
        values = [float(model_metrics[model_name][metric_name]) for model_name in model_names]
        plt.bar(x + (index - 1.5) * width, values, width=width, label=metric_name)

    plt.xticks(x, model_names)
    plt.ylim(0.0, 1.0)
    plt.title("Behavior model comparison")
    plt.ylabel("Score")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


class Command(BaseCommand):
    help = "Train and compare the sequence behavior classifiers."

    def handle(self, *args, **options):
        try:
            from sklearn.model_selection import train_test_split
        except ImportError as exc:
            raise CommandError(
                "Training dependencies are not installed. Install pandas and scikit-learn to train the behavior model."
            ) from exc

        try:
            import tensorflow as tf
        except ImportError as exc:
            raise CommandError("TensorFlow is required to train the behavior model.") from exc

        np.random.seed(RANDOM_STATE)
        if hasattr(tf.keras.utils, "set_random_seed"):
            tf.keras.utils.set_random_seed(RANDOM_STATE)
        else:
            tf.random.set_seed(RANDOM_STATE)

        rows, schema = _load_sequence_rows(DATASET_PATH)
        if not rows:
            raise CommandError("Training dataset is empty.")

        train_rows, validation_rows, test_rows = _split_sequence_rows(
            rows,
            validation_size=VALIDATION_SIZE,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
        )
        encoder, schema = _fit_sequence_encoder(train_rows, schema=schema)
        X_train, y_train, schema, encoder = _encode_rows_with_encoder(train_rows, schema=schema, encoder=encoder)
        X_validation, y_validation, _, _ = _encode_rows_with_encoder(
            validation_rows,
            schema=schema,
            encoder=encoder,
        )
        X_test, y_test, _, _ = _encode_rows_with_encoder(test_rows, schema=schema, encoder=encoder)
        metadata = _build_sequence_dataset_metadata(schema, encoder)

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        PLOTS_DIR.mkdir(parents=True, exist_ok=True)

        model_metrics = {}
        model_paths = {name: OUTPUT_DIR / filename for name, filename in MODEL_FILENAMES.items()}
        evaluation_paths = {}
        plot_paths = {}
        trained_models = {}

        for model_name in SEQUENCE_MODEL_PREFERENCE[::-1]:
            model = build_sequence_model(
                model_name,
                timesteps=X_train.shape[1],
                feature_dim=X_train.shape[2],
                output_dim=y_train.shape[1],
            )
            history = model.fit(X_train, y_train, epochs=EPOCHS, batch_size=BATCH_SIZE, verbose=0)
            validation_predictions = np.argmax(model.predict(X_validation, verbose=0), axis=1)
            validation_truth = np.argmax(y_validation, axis=1)
            validation_loss, validation_accuracy = model.evaluate(X_validation, y_validation, verbose=0)
            validation_precision = precision_score(
                validation_truth,
                validation_predictions,
                average="macro",
                zero_division=0,
            )
            validation_recall = recall_score(
                validation_truth,
                validation_predictions,
                average="macro",
                zero_division=0,
            )
            validation_f1 = f1_score(validation_truth, validation_predictions, average="macro", zero_division=0)

            test_predictions = np.argmax(model.predict(X_test, verbose=0), axis=1)
            test_truth = np.argmax(y_test, axis=1)
            test_loss, test_accuracy = model.evaluate(X_test, y_test, verbose=0)
            test_precision = precision_score(test_truth, test_predictions, average="macro", zero_division=0)
            test_recall = recall_score(test_truth, test_predictions, average="macro", zero_division=0)
            test_f1 = f1_score(test_truth, test_predictions, average="macro", zero_division=0)
            confusion = confusion_matrix(test_truth, test_predictions, labels=list(range(y_train.shape[1]))).tolist()
            report = classification_report(
                test_truth,
                test_predictions,
                labels=list(range(y_train.shape[1])),
                target_names=schema.labels,
                output_dict=True,
                zero_division=0,
            )
            model_metrics[model_name] = {
                "loss": float(validation_loss),
                "accuracy": float(validation_accuracy),
                "precision_macro": float(validation_precision),
                "recall_macro": float(validation_recall),
                "f1_macro": float(validation_f1),
                "validation_metrics": {
                    "loss": float(validation_loss),
                    "accuracy": float(validation_accuracy),
                    "precision_macro": float(validation_precision),
                    "recall_macro": float(validation_recall),
                    "f1_macro": float(validation_f1),
                },
                "test_metrics": {
                    "loss": float(test_loss),
                    "accuracy": float(test_accuracy),
                    "precision_macro": float(test_precision),
                    "recall_macro": float(test_recall),
                    "f1_macro": float(test_f1),
                },
            }
            trained_models[model_name] = model
            model.save(model_paths[model_name])
            evaluation_path = OUTPUT_DIR / f"model_{model_name}_evaluation.json"
            plot_path = PLOTS_DIR / f"training_history_{model_name}.png"
            evaluation_path.write_text(
                json.dumps(
                    _build_model_artifact_payload(
                        model_name=model_name,
                        validation_metrics=model_metrics[model_name]["validation_metrics"],
                        test_metrics=model_metrics[model_name]["test_metrics"],
                        labels=schema.labels,
                        confusion_matrix=confusion,
                        classification_report=report,
                        history=getattr(history, "history", {}),
                    ),
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            _save_training_history_plot(history, plot_path, model_name)
            evaluation_paths[model_name] = evaluation_path
            plot_paths[model_name] = plot_path

        best_model_name = _select_best_model_from_validation(
            {name: metrics["validation_metrics"] for name, metrics in model_metrics.items()},
            {name: metrics["test_metrics"] for name, metrics in model_metrics.items()},
        )
        best_model_path = OUTPUT_DIR / BEST_MODEL_FILENAME
        trained_models[best_model_name].save(best_model_path)

        comparison_path = OUTPUT_DIR / COMPARISON_FILENAME
        metadata_path = OUTPUT_DIR / METADATA_FILENAME
        comparison_payload = _build_comparison_payload(DATASET_PATH, best_model_name, model_metrics)
        comparison_path.write_text(
            json.dumps(comparison_payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        comparison_plot_path = PLOTS_DIR / "model_comparison.png"
        _save_comparison_plot(model_metrics, comparison_plot_path)
        comparison_payload["plot_path"] = _portable_path(comparison_plot_path)
        comparison_payload["comparison_path"] = _portable_path(comparison_path)
        metadata = _build_sequence_metadata(
            schema=schema,
            dataset_path=DATASET_PATH,
            model_paths={**model_paths, best_model_name: best_model_path},
            comparison_path=comparison_path,
            evaluation_paths=evaluation_paths,
            plot_paths={**plot_paths, "comparison": comparison_plot_path},
            best_model_name=best_model_name,
            training_rows=len(train_rows),
            validation_rows=len(validation_rows),
            test_rows=len(X_test),
            encoder=metadata["encoder"],
        )
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        comparison_path.write_text(json.dumps(comparison_payload, indent=2, sort_keys=True), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Best model={best_model_name} f1_macro={model_metrics[best_model_name]['f1_macro']:.3f} "
                f"accuracy={model_metrics[best_model_name]['accuracy']:.3f}"
            )
        )
