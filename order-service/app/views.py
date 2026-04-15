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
ORDER_STATUS_TRANSITIONS = {
    "pending": ["confirmed", "paid", "cancelled"],
    "confirmed": ["paid", "cancelled"],
    "paid": ["shipping", "cancelled"],
    "shipping": ["delivered"],
    "delivered": [],
    "cancelled": [],
}


def _order_items_payload(order):
    return [{"book_id": item.book_id, "quantity": item.quantity} for item in order.items.all()]


def _normalize_order_items(items):
    if not isinstance(items, list) or not items:
        raise ValueError("Order items are required")

    normalized_items = []
    total = Decimal("0.00")

    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each order item must be an object")

        try:
            book_id = int(item["book_id"])
            quantity = int(item["quantity"])
            book_title = str(item["book_title"]).strip()
            unit_price = Decimal(str(item["unit_price"]))
        except (KeyError, TypeError, ValueError):
            raise ValueError("Order items must include book_id, quantity, book_title, and unit_price")

        if quantity <= 0:
            raise ValueError("Order item quantity must be positive")
        if not book_title:
            raise ValueError("Order item title is required")
        if unit_price < 0:
            raise ValueError("Order item price must not be negative")

        normalized_items.append(
            {
                "book_id": book_id,
                "quantity": quantity,
                "book_title": book_title,
                "unit_price": unit_price,
            }
        )
        total += unit_price * quantity

    return normalized_items, total


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

    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            items, total = _normalize_order_items(request.data.get("items"))
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.create(
            user_id=serializer.validated_data["user_id"],
            status="pending",
            total_amount=total,
            shipping_name=serializer.validated_data["shipping_name"],
            shipping_phone=serializer.validated_data["shipping_phone"],
            shipping_address=serializer.validated_data["shipping_address"],
            note=serializer.validated_data.get("note", ""),
        )
        for item_data in items:
            OrderItem.objects.create(order=order, **item_data)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderDetailView(APIView):
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        return Response(OrderSerializer(order).data)


class CheckoutView(APIView):
    def post(self, request):
        return OrderListView().post(request)


class UpdateOrderStatusView(APIView):
    def put(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        new_status = request.data.get("status")
        allowed = ORDER_STATUS_TRANSITIONS.get(order.status, [])
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
