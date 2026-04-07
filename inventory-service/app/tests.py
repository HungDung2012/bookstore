from django.test import TestCase
from rest_framework.test import APIClient

from .models import InventoryItem


class InventoryReservationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_reserve_rolls_back_when_one_item_is_insufficient(self):
        first = InventoryItem.objects.create(book_id=1, quantity=5, reserved=0)
        InventoryItem.objects.create(book_id=2, quantity=1, reserved=0)

        response = self.client.post(
            "/inventory/reserve/",
            {
                "items": [
                    {"book_id": 1, "quantity": 2},
                    {"book_id": 2, "quantity": 2},
                ]
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        first.refresh_from_db()
        self.assertEqual(first.reserved, 0)

    def test_restock_restores_quantity(self):
        item = InventoryItem.objects.create(book_id=10, quantity=3, reserved=0)

        response = self.client.post(
            "/inventory/restock/",
            {"items": [{"book_id": 10, "quantity": 4}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.quantity, 7)
