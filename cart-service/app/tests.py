from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from .models import Cart, CartItem


class CartItemTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    @patch("app.views.requests.get")
    def test_add_item_uses_existing_customer_cart(self, mock_get):
        cart = Cart.objects.create(customer_id=7)

        books_response = Mock(status_code=200)
        books_response.json.return_value = [{"id": 3, "title": "Demo"}]
        books_response.raise_for_status.return_value = None
        mock_get.return_value = books_response

        response = self.client.post(
            "/cart-items/",
            {"cart": 7, "book_id": 3, "quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Cart.objects.count(), 1)
        item = CartItem.objects.get(cart=cart, book_id=3)
        self.assertEqual(item.quantity, 2)

    @patch("app.views.requests.get")
    def test_add_item_merges_quantity_for_existing_cart_item(self, mock_get):
        cart = Cart.objects.create(customer_id=9)
        CartItem.objects.create(cart=cart, book_id=5, quantity=1)

        books_response = Mock(status_code=200)
        books_response.json.return_value = [{"id": 5, "title": "Demo"}]
        books_response.raise_for_status.return_value = None
        mock_get.return_value = books_response

        response = self.client.post(
            "/cart-items/",
            {"cart": 9, "book_id": 5, "quantity": 4},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        item = CartItem.objects.get(cart=cart, book_id=5)
        self.assertEqual(item.quantity, 5)
