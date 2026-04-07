from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Order, OrderItem


class OrderStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("app.views.requests.post")
    def test_pending_order_can_move_to_paid_and_confirms_inventory(self, mock_post):
        confirm_response = Mock(status_code=200)
        mock_post.return_value = confirm_response

        order = Order.objects.create(
            user_id=1,
            status="pending",
            total_amount="20.00",
            shipping_name="Alice",
            shipping_phone="0123",
            shipping_address="123 Street",
        )
        OrderItem.objects.create(
            order=order,
            book_id=9,
            book_title="Book",
            quantity=2,
            unit_price="10.00",
        )

        response = self.client.put(f"/orders/{order.id}/status/", {"status": "paid"}, format="json")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")
        mock_post.assert_called_once_with(
            "http://inventory-service:8000/inventory/confirm/",
            json={"items": [{"book_id": 9, "quantity": 2}]},
            timeout=5,
        )

    @patch("app.views.requests.post")
    def test_cancelling_confirmed_order_restocks_inventory(self, mock_post):
        mock_post.return_value = Mock(status_code=200)

        order = Order.objects.create(
            user_id=1,
            status="confirmed",
            total_amount="15.00",
            shipping_name="Alice",
            shipping_phone="0123",
            shipping_address="123 Street",
        )
        OrderItem.objects.create(
            order=order,
            book_id=4,
            book_title="Book",
            quantity=1,
            unit_price="15.00",
        )

        response = self.client.post(f"/orders/{order.id}/cancel/")

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        mock_post.assert_called_once_with(
            "http://inventory-service:8000/inventory/restock/",
            json={"items": [{"book_id": 4, "quantity": 1}]},
            timeout=5,
        )
