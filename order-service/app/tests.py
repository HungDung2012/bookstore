from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Order, OrderItem


class OrderStatusTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_order_service_creates_order_from_cart_payload(self):
        response = self.client.post(
            "/orders/",
            {
                "user_id": 3,
                "shipping_name": "Customer One",
                "shipping_phone": "0900000000",
                "shipping_address": "123 Main St",
                "payment_method": "cod",
                "note": "Leave at front desk",
                "items": [
                    {
                        "book_id": 1,
                        "quantity": 2,
                        "book_title": "Dune",
                        "unit_price": "19.99",
                    },
                    {
                        "book_id": 5,
                        "quantity": 1,
                        "book_title": "Sapiens",
                        "unit_price": "14.50",
                    },
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["user_id"], 3)
        self.assertEqual(response.data["status"], "pending")
        self.assertEqual(response.data["shipping_name"], "Customer One")
        self.assertEqual(response.data["total_amount"], "54.48")
        self.assertEqual(len(response.data["items"]), 2)

        order = Order.objects.get()
        self.assertEqual(order.user_id, 3)
        self.assertEqual(order.status, "pending")
        self.assertEqual(str(order.total_amount), "54.48")
        self.assertEqual(order.items.count(), 2)

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

        response = self.client.put(
            f"/orders/{order.id}/status/",
            {"status": "paid"},
            format="json",
            HTTP_X_INTERNAL_SERVICE_TOKEN="gateway-internal-token",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "paid")
        mock_post.assert_called_once_with(
            "http://inventory-service:8000/inventory/confirm/",
            json={"items": [{"book_id": 9, "quantity": 2}]},
            timeout=5,
        )

    @patch("app.views.requests.post")
    def test_pending_order_can_move_to_confirmed_without_inventory_sync(self, mock_post):
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

        response = self.client.put(
            f"/orders/{order.id}/status/",
            {"status": "confirmed"},
            format="json",
            HTTP_X_INTERNAL_SERVICE_TOKEN="gateway-internal-token",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")
        mock_post.assert_not_called()

    def test_status_update_rejects_requests_without_internal_service_token(self):
        order = Order.objects.create(
            user_id=1,
            status="pending",
            total_amount="20.00",
            shipping_name="Alice",
            shipping_phone="0123",
            shipping_address="123 Street",
        )

        response = self.client.put(f"/orders/{order.id}/status/", {"status": "confirmed"}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"], "Forbidden")

    @patch.dict("os.environ", {"ORDER_SERVICE_INTERNAL_TOKEN": "shared-secret"})
    def test_status_update_accepts_requests_with_matching_internal_service_token(self):
        order = Order.objects.create(
            user_id=1,
            status="pending",
            total_amount="20.00",
            shipping_name="Alice",
            shipping_phone="0123",
            shipping_address="123 Street",
        )

        response = self.client.put(
            f"/orders/{order.id}/status/",
            {"status": "confirmed"},
            format="json",
            HTTP_X_INTERNAL_SERVICE_TOKEN="shared-secret",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "confirmed")

    @patch("app.views.requests.post")
    def test_cancelling_confirmed_order_does_not_touch_inventory(self, mock_post):
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
        mock_post.assert_not_called()

    @patch("app.views.requests.post")
    def test_cancelling_paid_order_restocks_inventory(self, mock_post):
        mock_post.return_value = Mock(status_code=200)

        order = Order.objects.create(
            user_id=1,
            status="paid",
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
