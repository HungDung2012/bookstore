import os
from decimal import Decimal

import requests
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Order, OrderItem
from .serializers import CheckoutSerializer, OrderSerializer


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


CART_SERVICE_URL = _service_url("CART_SERVICE_URL", "cart-service:8000")
BOOK_SERVICE_URL = _service_url("BOOK_SERVICE_URL", "book-service:8000")
INVENTORY_SERVICE_URL = _service_url("INVENTORY_SERVICE_URL", "inventory-service:8000")
PAYMENT_SERVICE_URL = _service_url("PAYMENT_SERVICE_URL", "payment-service:8000")


def _order_items_payload(order):
    return [{"book_id": item.book_id, "quantity": item.quantity} for item in order.items.all()]


def _sync_inventory_for_cancellation(order):
    items = _order_items_payload(order)
    if not items:
        return

    endpoint = "/inventory/release/" if order.status == "pending" else "/inventory/restock/"
    try:
        requests.post(
            f"{INVENTORY_SERVICE_URL}{endpoint}",
            json={"items": items},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        pass


class OrderListView(APIView):
    def get(self, request):
        user_id = request.query_params.get("user_id")
        if user_id:
            orders = Order.objects.filter(user_id=user_id).order_by("-created_at")
        else:
            orders = Order.objects.all().order_by("-created_at")
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class OrderDetailView(APIView):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        return Response(OrderSerializer(order).data)


class CheckoutView(APIView):
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        user_id = data["user_id"]
        payment_method = data["payment_method"]

        try:
            cart_resp = requests.get(f"{CART_SERVICE_URL}/carts/{user_id}/", timeout=5)
            if cart_resp.status_code != 200:
                return Response(
                    {"error": "Cart not found or empty"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            cart_items = cart_resp.json()
            if not cart_items:
                return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as exc:
            return Response(
                {"error": f"Cart service unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            books_resp = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            books_resp.raise_for_status()
            books = {book["id"]: book for book in books_resp.json()}
        except requests.exceptions.RequestException as exc:
            return Response(
                {"error": f"Book service unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        order_items_data = []
        inventory_items = []
        total = Decimal("0.00")

        for item in cart_items:
            book_id = item["book_id"]
            quantity = item["quantity"]
            book = books.get(book_id)
            if not book:
                return Response(
                    {"error": f"Book {book_id} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            price = Decimal(str(book["price"]))
            total += price * quantity
            order_items_data.append(
                {
                    "book_id": book_id,
                    "book_title": book["title"],
                    "quantity": quantity,
                    "unit_price": price,
                }
            )
            inventory_items.append({"book_id": book_id, "quantity": quantity})

        try:
            reserve_resp = requests.post(
                f"{INVENTORY_SERVICE_URL}/inventory/reserve/",
                json={"items": inventory_items},
                timeout=5,
            )
            if reserve_resp.status_code != 200:
                error = reserve_resp.json().get("error", "Stock reservation failed")
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as exc:
            return Response(
                {"error": f"Inventory service unavailable: {exc}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        order = Order.objects.create(
            user_id=user_id,
            status="pending",
            total_amount=total,
            shipping_name=data["shipping_name"],
            shipping_phone=data["shipping_phone"],
            shipping_address=data["shipping_address"],
            note=data.get("note", ""),
        )
        for item_data in order_items_data:
            OrderItem.objects.create(order=order, **item_data)

        try:
            payment_resp = requests.post(
                f"{PAYMENT_SERVICE_URL}/payments/",
                json={
                    "order_id": order.id,
                    "amount": str(total),
                    "method": payment_method,
                },
                timeout=5,
            )
            if payment_resp.status_code not in (status.HTTP_200_OK, status.HTTP_201_CREATED):
                raise requests.exceptions.RequestException(payment_resp.text)

            if payment_method == "cod":
                confirm_resp = requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/confirm/",
                    json={"items": inventory_items},
                    timeout=5,
                )
                if confirm_resp.status_code != 200:
                    order.status = "cancelled"
                    order.save(update_fields=["status", "updated_at"])
                    requests.post(
                        f"{INVENTORY_SERVICE_URL}/inventory/release/",
                        json={"items": inventory_items},
                        timeout=5,
                    )
                    return Response(
                        {"error": "Could not finalize inventory deduction"},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE,
                    )
                order.status = "confirmed"
                order.save(update_fields=["status", "updated_at"])

            try:
                requests.delete(f"{CART_SERVICE_URL}/carts/{user_id}/clear/", timeout=5)
            except requests.exceptions.RequestException:
                pass

        except requests.exceptions.RequestException:
            order.status = "cancelled"
            order.save(update_fields=["status", "updated_at"])
            try:
                requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/release/",
                    json={"items": inventory_items},
                    timeout=5,
                )
            except requests.exceptions.RequestException:
                pass
            return Response(
                {"error": "Payment service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class UpdateOrderStatusView(APIView):
    def put(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        new_status = request.data.get("status")
        valid_transitions = {
            "pending": ["confirmed", "paid", "cancelled"],
            "confirmed": ["paid", "cancelled"],
            "paid": ["shipping", "cancelled"],
            "shipping": ["delivered"],
            "delivered": [],
            "cancelled": [],
        }
        allowed = valid_transitions.get(order.status, [])
        if new_status not in allowed:
            return Response(
                {"error": f"Cannot change from '{order.status}' to '{new_status}'. Allowed: {allowed}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_status == "paid" and order.status == "pending":
            try:
                confirm_resp = requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/confirm/",
                    json={"items": _order_items_payload(order)},
                    timeout=5,
                )
            except requests.exceptions.RequestException:
                return Response(
                    {"error": "Inventory service unavailable during payment confirmation"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            if confirm_resp.status_code != 200:
                return Response(
                    {"error": "Could not confirm inventory for payment"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

        if new_status == "cancelled":
            _sync_inventory_for_cancellation(order)

        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order).data)


class CancelOrderView(APIView):
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if order.status in ("delivered", "cancelled"):
            return Response(
                {"error": f"Cannot cancel order with status '{order.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _sync_inventory_for_cancellation(order)
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
        return Response(OrderSerializer(order).data)
