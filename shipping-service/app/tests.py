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
            {"status": "shipping"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "shipping")
