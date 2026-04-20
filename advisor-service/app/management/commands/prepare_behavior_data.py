import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from app.services.behavior_dataset import BehaviorDatasetSchema
from app.services.clients import UpstreamClient
from app.services.features import build_behavior_features, infer_behavior_label

OUTPUT_PATH = Path(__file__).resolve().parents[2] / "data" / "training" / "behavior_dataset.csv"


class Command(BaseCommand):
    help = "Prepare behavior training data from upstream microservices."

    def handle(self, *args, **options):
        client = UpstreamClient()
        try:
            books = client.get_books()
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"Skipping export: failed to load books ({exc})"))
            return

        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for user_id in range(1, 21):
            try:
                profile = client.get_user(user_id)
                orders = client.get_orders(user_id)
                reviews = client.get_reviews(user_id)
                cart_items = client.get_cart(user_id)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Skipping user {user_id}: {exc}"))
                continue

            features = build_behavior_features(profile, books, orders, reviews, cart_items)
            rows.append({**features, "label": infer_behavior_label(features)})

        if not rows:
            self.stdout.write(self.style.WARNING("No rows generated"))
            return

        schema = BehaviorDatasetSchema.from_rows(rows)
        with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=schema.export_fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(schema.build_record(row, row["label"]))

        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} rows to {OUTPUT_PATH}"))
