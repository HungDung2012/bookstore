import json
import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from app.services.behavior_dataset import (
    BehaviorSequenceSchema,
    generate_behavior_sequence_rows,
)

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "training" / "data_user500.csv"
USER_COUNT = 500
SAMPLE_COUNT = 20
SEQUENCE_LENGTH = 8
SEQUENCE_SEED = 500


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _build_metadata(schema, output_path, sample_path, metadata_path, rows, sample_rows):
    return {
        **schema.to_metadata(),
        "dataset_file": output_path.name,
        "sample_file": sample_path.name,
        "metadata_file": metadata_path.name,
        "user_count": len(rows),
        "sample_count": len(sample_rows),
        "seed": SEQUENCE_SEED,
    }


class Command(BaseCommand):
    help = "Prepare synthetic behavior sequence training data."

    def handle(self, *args, **options):
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        rows = generate_behavior_sequence_rows(
            user_count=USER_COUNT,
            step_count=SEQUENCE_LENGTH,
            seed=SEQUENCE_SEED,
        )

        if not rows:
            self.stdout.write(self.style.WARNING("No rows generated"))
            return

        schema = BehaviorSequenceSchema.from_rows(rows)
        sample_rows = rows[:SAMPLE_COUNT]
        sample_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_sample20{OUTPUT_PATH.suffix}")
        metadata_path = OUTPUT_PATH.with_name(f"{OUTPUT_PATH.stem}_metadata.json")

        _write_csv(
            OUTPUT_PATH,
            schema.export_fieldnames,
            [schema.build_record(row, row["label"]) for row in rows],
        )
        _write_csv(
            sample_path,
            schema.export_fieldnames,
            [schema.build_record(row, row["label"]) for row in sample_rows],
        )

        metadata = _build_metadata(schema, OUTPUT_PATH, sample_path, metadata_path, rows, sample_rows)
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

        self.stdout.write(
            self.style.SUCCESS(
                f"Wrote {len(rows)} users to {OUTPUT_PATH}, {len(sample_rows)} users to {sample_path}, and metadata to {metadata_path}"
            )
        )
