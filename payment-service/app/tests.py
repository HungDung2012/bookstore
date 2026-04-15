from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Payment


class PaymentDemoFlowTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("app.views.requests.put")
    def test_payment_service_returns_success_for_demo_success_method(self, put_mock):
        response = self.client.post(
            "/payments/",
            {"order_id": 101, "amount": "19.99", "method": "demo_success"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message"], "Demo payment successful")
        self.assertEqual(response.data["payment"]["status"], "completed")

        payment = Payment.objects.get(order_id=101)
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.amount, Decimal("19.99"))
        put_mock.assert_called_once_with(
            "http://order-service:8000/orders/101/status/",
            json={"status": "paid"},
            timeout=5,
        )

    @patch("app.views.requests.put")
    def test_payment_service_returns_failure_for_demo_fail_method(self, put_mock):
        response = self.client.post(
            "/payments/",
            {"order_id": 102, "amount": "19.99", "method": "demo_fail"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message"], "Demo payment failed")
        self.assertEqual(response.data["payment"]["status"], "failed")

        payment = Payment.objects.get(order_id=102)
        self.assertEqual(payment.status, "failed")
        put_mock.assert_called_once_with(
            "http://order-service:8000/orders/102/status/",
            json={"status": "cancelled"},
            timeout=5,
        )
