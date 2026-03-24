import os

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
NOTIFICATION_SERVICE_URL = _service_url("NOTIFICATION_SERVICE_URL", "notification-service:8000")


class OrderListView(APIView):
    """GET /orders/?user_id=X — Danh sách đơn hàng của user"""
    def get(self, request):
        user_id = request.query_params.get('user_id')
        if user_id:
            orders = Order.objects.filter(user_id=user_id).order_by('-created_at')
        else:
            orders = Order.objects.all().order_by('-created_at')
        serializer = OrderSerializer(orders, many=True)
        return Response(serializer.data)


class OrderDetailView(APIView):
    """GET /orders/<id>/ — Chi tiết đơn hàng"""
    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        return Response(OrderSerializer(order).data)


class CheckoutView(APIView):
    """POST /orders/checkout/ — Quy trình đặt hàng (Saga Pattern)
    
    Saga steps:
    1. Lấy giỏ hàng từ Cart Service
    2. Lấy thông tin sách từ Book Service (snapshot giá)
    3. Reserve stock từ Inventory Service
    4. Tạo Order (status=pending)
    5. Gọi Payment Service tạo payment
    6. Nếu COD → confirm ngay, nếu online → chờ callback
    """
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        user_id = data['user_id']
        payment_method = data['payment_method']
        
        # Step 1: Lấy giỏ hàng
        try:
            cart_resp = requests.get(f"{CART_SERVICE_URL}/carts/{user_id}/", timeout=5)
            if cart_resp.status_code != 200:
                return Response({"error": "Cart not found or empty"}, status=status.HTTP_400_BAD_REQUEST)
            cart_items = cart_resp.json()
            if not cart_items:
                return Response({"error": "Cart is empty"}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Cart service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        # Step 2: Lấy thông tin sách (snapshot giá)
        try:
            books_resp = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            books_resp.raise_for_status()
            books = {b['id']: b for b in books_resp.json()}
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Book service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        # Build order items with price snapshots
        order_items_data = []
        inventory_items = []
        total = 0
        for item in cart_items:
            book_id = item['book_id']
            qty = item['quantity']
            book = books.get(book_id)
            if not book:
                return Response({"error": f"Book {book_id} not found"}, status=status.HTTP_400_BAD_REQUEST)
            price = float(book['price'])
            total += price * qty
            order_items_data.append({
                'book_id': book_id,
                'book_title': book['title'],
                'quantity': qty,
                'unit_price': price,
            })
            inventory_items.append({'book_id': book_id, 'quantity': qty})
        
        # Step 3: Reserve stock
        try:
            reserve_resp = requests.post(
                f"{INVENTORY_SERVICE_URL}/inventory/reserve/",
                json={"items": inventory_items}, timeout=5
            )
            if reserve_resp.status_code != 200:
                error = reserve_resp.json().get('error', 'Stock reservation failed')
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Inventory service unavailable: {e}"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        
        # Step 4: Tạo Order
        order = Order.objects.create(
            user_id=user_id,
            status='pending',
            total_amount=total,
            shipping_name=data['shipping_name'],
            shipping_phone=data['shipping_phone'],
            shipping_address=data['shipping_address'],
            note=data.get('note', ''),
        )
        for item_data in order_items_data:
            OrderItem.objects.create(order=order, **item_data)
        
        # Step 5: Tạo Payment
        try:
            payment_resp = requests.post(
                f"{PAYMENT_SERVICE_URL}/payments/",
                json={
                    "order_id": order.id,
                    "amount": float(total),
                    "method": payment_method,
                }, timeout=5
            )
            
            if payment_method == 'cod':
                # COD: confirm ngay lập tức
                order.status = 'confirmed'
                order.save()
                # Confirm deduction
                try:
                    requests.post(
                        f"{INVENTORY_SERVICE_URL}/inventory/confirm/",
                        json={"items": inventory_items}, timeout=5
                    )
                except requests.exceptions.RequestException:
                    pass
            else:
                # Online payment: giữ pending, chờ callback
                order.status = 'pending'
                order.save()
                
        except requests.exceptions.RequestException:
            # Payment service down → release stock, cancel order
            order.status = 'cancelled'
            order.save()
            try:
                requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/release/",
                    json={"items": inventory_items}, timeout=5
                )
            except requests.exceptions.RequestException:
                pass
            return Response({"error": "Payment service unavailable"}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class UpdateOrderStatusView(APIView):
    """PUT /orders/<id>/status/ — Cập nhật trạng thái đơn hàng"""
    def put(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        new_status = request.data.get('status')
        valid_transitions = {
            'pending': ['confirmed', 'cancelled'],
            'confirmed': ['paid', 'cancelled'],
            'paid': ['shipping', 'cancelled'],
            'shipping': ['delivered'],
            'delivered': [],
            'cancelled': [],
        }
        allowed = valid_transitions.get(order.status, [])
        if new_status not in allowed:
            return Response(
                {"error": f"Cannot change from '{order.status}' to '{new_status}'. Allowed: {allowed}"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # If cancelling, release inventory
        if new_status == 'cancelled' and order.status in ('pending', 'confirmed'):
            items = [{'book_id': i.book_id, 'quantity': i.quantity} for i in order.items.all()]
            try:
                requests.post(
                    f"{INVENTORY_SERVICE_URL}/inventory/release/",
                    json={"items": items}, timeout=5
                )
            except requests.exceptions.RequestException:
                pass
        
        order.status = new_status
        order.save()
        return Response(OrderSerializer(order).data)


class CancelOrderView(APIView):
    """POST /orders/<id>/cancel/ — Hủy đơn hàng"""
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk)
        if order.status in ('delivered', 'cancelled'):
            return Response({"error": f"Cannot cancel order with status '{order.status}'"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Release inventory
        items = [{'book_id': i.book_id, 'quantity': i.quantity} for i in order.items.all()]
        try:
            requests.post(
                f"{INVENTORY_SERVICE_URL}/inventory/release/",
                json={"items": items}, timeout=5
            )
        except requests.exceptions.RequestException:
            pass
        
        order.status = 'cancelled'
        order.save()
        return Response(OrderSerializer(order).data)
