import os
import sys

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "inventory_service.settings")
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from app.models import InventoryItem


items = [
    (1, 50),
    (2, 80),
    (3, 65),
    (4, 70),
    (5, 90),
    (6, 45),
    (7, 60),
    (8, 40),
    (9, 55),
    (10, 100),
    (11, 35),
    (12, 42),
    (13, 75),
    (14, 50),
    (15, 60),
    (16, 45),
    (17, 80),
    (18, 55),
]

for book_id, qty in items:
    InventoryItem.objects.update_or_create(
        book_id=book_id,
        defaults={"quantity": qty, "reserved": 0},
    )

print(f"Seeded {InventoryItem.objects.count()} inventory items")
