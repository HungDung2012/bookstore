from django.test import TestCase
from rest_framework.test import APIClient

from .models import Shipment


class ShipmentWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_create_shipment_for_order(self):
        response = self.client.post(
            "/shipping/",
            {"order_id": 10, "status": "pending"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)

    def test_staff_can_update_shipping_status(self):
        shipment = Shipment.objects.create(order_id=10, status="pending")

        response = self.client.patch(
            f"/shipping/{shipment.id}/",
            {"status": "packed"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "packed")

    def test_staff_cannot_skip_shipping_status_progression(self):
        shipment = Shipment.objects.create(order_id=11, status="pending")

        response = self.client.patch(
            f"/shipping/{shipment.id}/",
            {"status": "shipping"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, "pending")

    def test_patch_does_not_allow_reassigning_order_id(self):
        shipment = Shipment.objects.create(order_id=12, status="pending")

        response = self.client.patch(
            f"/shipping/{shipment.id}/",
            {"order_id": 99},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        shipment.refresh_from_db()
        self.assertEqual(shipment.order_id, 12)
