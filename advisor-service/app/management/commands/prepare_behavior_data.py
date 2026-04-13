import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from app.services.clients import UpstreamClient
from app.services.features import build_behavior_features, infer_behavior_label


class Command(BaseCommand):
    help = "Prepare behavior training data from upstream microservices."

    def handle(self, *args, **options):
        client = UpstreamClient()
        books = client.get_books()
        output_path = Path("app/data/training/behavior_dataset.csv")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rows = []
        for user_id in range(1, 21):
            try:
                profile = client.get_user(user_id)
                orders = client.get_orders(user_id)
                reviews = client.get_reviews(user_id)
                cart_items = client.get_cart(user_id)
            except Exception:
                continue

            features = build_behavior_features(profile, books, orders, reviews, cart_items)
            features["label"] = infer_behavior_label(features)
            rows.append(features)

        if not rows:
            self.stdout.write(self.style.WARNING("No rows generated"))
            return

        fieldnames = sorted({key for row in rows for key in row.keys()})
        with output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        self.stdout.write(self.style.SUCCESS(f"Wrote {len(rows)} rows to {output_path}"))
