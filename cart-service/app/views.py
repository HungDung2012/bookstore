import os

import requests
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Cart, CartItem
from .serializers import CartItemSerializer, CartSerializer


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


BOOK_SERVICE_URL = _service_url("BOOK_SERVICE_URL", "book-service:8000")


def _resolve_cart(cart_identifier):
    if cart_identifier in (None, ""):
        return None

    try:
        cart_id = int(cart_identifier)
    except (TypeError, ValueError):
        return None

    cart = Cart.objects.filter(id=cart_id).first()
    if cart:
        return cart

    cart, _ = Cart.objects.get_or_create(customer_id=cart_id)
    return cart


def _resolve_customer_cart(customer_identifier):
    if customer_identifier in (None, ""):
        return None

    try:
        customer_id = int(customer_identifier)
    except (TypeError, ValueError):
        return None

    cart, _ = Cart.objects.get_or_create(customer_id=customer_id)
    return cart


class CartCreate(APIView):
    def post(self, request):
        customer_id = request.data.get("customer_id")
        if customer_id in (None, ""):
            return Response({"error": "customer_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        cart, created = Cart.objects.get_or_create(customer_id=customer_id)
        serializer = CartSerializer(cart)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class AddCartItem(APIView):
    def post(self, request):
        book_id = request.data.get("book_id")
        quantity = request.data.get("quantity", 1)
        customer_id = request.data.get("customer_id")
        cart_identifier = request.data.get("cart")

        if customer_id in (None, ""):
            return Response(
                {"error": "customer_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        cart = _resolve_customer_cart(customer_id)
        if cart is None:
            return Response({"error": "customer_id must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        if cart_identifier not in (None, ""):
            requested_cart = _resolve_cart(cart_identifier)
            if requested_cart is None:
                return Response({"error": "cart must be an integer"}, status=status.HTTP_400_BAD_REQUEST)
            if requested_cart.customer_id != cart.customer_id:
                return Response(
                    {"error": "You cannot modify another user's cart"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            cart = requested_cart

        if cart is None:
            return Response(
                {"error": "customer_id is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = int(quantity)
            book_id = int(book_id)
        except (TypeError, ValueError):
            return Response(
                {"error": "book_id and quantity must be integers"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if quantity <= 0:
            return Response({"error": "quantity must be positive"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            response = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            response.raise_for_status()
            books = response.json()
            if not any(book["id"] == book_id for book in books):
                return Response({"error": "Book not found"}, status=status.HTTP_404_NOT_FOUND)
        except requests.exceptions.RequestException as exc:
            return Response(
                {"error": f"Error contacting book-service: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        existing = CartItem.objects.filter(cart=cart, book_id=book_id).first()
        if existing:
            existing.quantity += quantity
            existing.save(update_fields=["quantity"])
            return Response(CartItemSerializer(existing).data)

        serializer = CartItemSerializer(data={"cart": cart.id, "book_id": book_id, "quantity": quantity})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ViewCart(APIView):
    def get(self, request, customer_id):
        cart = Cart.objects.filter(customer_id=customer_id).first()
        if not cart:
            return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

        items = CartItem.objects.filter(cart=cart)
        serializer = CartItemSerializer(items, many=True)
        return Response(serializer.data)


class UpdateCartItem(APIView):
    def put(self, request, customer_id):
        cart = Cart.objects.filter(customer_id=customer_id).first()
        if not cart:
            return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

        book_id = request.data.get("book_id")
        quantity = request.data.get("quantity")
        if not book_id or quantity is None:
            return Response(
                {"error": "book_id and quantity are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            quantity = int(quantity)
        except (TypeError, ValueError):
            return Response({"error": "quantity must be an integer"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = CartItem.objects.get(cart=cart, book_id=book_id)
        except CartItem.DoesNotExist:
            return Response({"error": "Item not found in cart"}, status=status.HTTP_404_NOT_FOUND)

        if quantity <= 0:
            cart_item.delete()
            return Response({"message": "Item removed from cart"})

        cart_item.quantity = quantity
        cart_item.save(update_fields=["quantity"])
        return Response(CartItemSerializer(cart_item).data)


class DeleteCartItem(APIView):
    def delete(self, request, customer_id, item_id):
        cart = Cart.objects.filter(customer_id=customer_id).first()
        if not cart:
            return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
        except CartItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=status.HTTP_404_NOT_FOUND)

        cart_item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClearCart(APIView):
    def delete(self, request, customer_id):
        cart = Cart.objects.filter(customer_id=customer_id).first()
        if not cart:
            return Response({"error": "Cart not found"}, status=status.HTTP_404_NOT_FOUND)

        CartItem.objects.filter(cart=cart).delete()
        return Response({"message": "Cart cleared"})
