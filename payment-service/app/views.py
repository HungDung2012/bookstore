import os

import requests
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment
from .serializers import PaymentCreateSerializer, PaymentSerializer


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


ORDER_SERVICE_URL = _service_url("ORDER_SERVICE_URL", "order-service:8000")
INVENTORY_SERVICE_URL = _service_url("INVENTORY_SERVICE_URL", "inventory-service:8000")


class PaymentListCreate(APIView):
    """GET /payments/?order_id=X — Danh sách payment
       POST /payments/ — Tạo payment mới (gọi bởi Order Service)"""
    def get(self, request):
        order_id = request.query_params.get('order_id')
        if order_id:
            payments = Payment.objects.filter(order_id=order_id)
        else:
            payments = Payment.objects.all().order_by('-created_at')
        return Response(PaymentSerializer(payments, many=True).data)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        
        # Check if payment already exists for this order
        if Payment.objects.filter(order_id=data['order_id']).exists():
            existing = Payment.objects.get(order_id=data['order_id'])
            return Response(PaymentSerializer(existing).data)
        
        payment = Payment.objects.create(**data)
        
        # If COD, auto-complete
        if data['method'] == 'cod':
            payment.status = 'completed'
            payment.save()
        
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    """GET /payments/<id>/ — Chi tiết payment"""
    def get(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        return Response(PaymentSerializer(payment).data)


class ProcessPaymentView(APIView):
    """POST /payments/<id>/process/ — Mô phỏng xử lý thanh toán online
    
    Trong thực tế, đây là callback từ VNPay/MoMo.
    Ở đây ta mô phỏng bằng cách gọi trực tiếp.
    """
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        
        if payment.status != 'pending':
            return Response(
                {"error": f"Payment is already '{payment.status}'"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Simulate: accept = True (always succeed for demo)
        success = request.data.get('success', True)
        
        if success:
            payment.status = 'completed'
            payment.save()
            
            # Notify Order Service to update status
            try:
                requests.put(
                    f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                    json={"status": "paid"}, timeout=5
                )
            except requests.exceptions.RequestException:
                pass
            
            return Response({
                "message": "Payment successful",
                "payment": PaymentSerializer(payment).data,
            })
        else:
            payment.status = 'failed'
            payment.save()
            
            # Release inventory and cancel order
            try:
                # Get order items to release
                order_resp = requests.get(f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/", timeout=5)
                if order_resp.status_code == 200:
                    order_data = order_resp.json()
                    items = [{'book_id': i['book_id'], 'quantity': i['quantity']} for i in order_data.get('items', [])]
                    requests.post(f"{INVENTORY_SERVICE_URL}/inventory/release/", json={"items": items}, timeout=5)
                
                requests.put(
                    f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                    json={"status": "cancelled"}, timeout=5
                )
            except requests.exceptions.RequestException:
                pass
            
            return Response({
                "message": "Payment failed",
                "payment": PaymentSerializer(payment).data,
            }, status=status.HTTP_400_BAD_REQUEST)


class RefundView(APIView):
    """POST /payments/<id>/refund/ — Hoàn tiền"""
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        
        if payment.status != 'completed':
            return Response(
                {"error": "Can only refund completed payments"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        payment.status = 'refunded'
        payment.save()
        
        # Release inventory
        try:
            order_resp = requests.get(f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/", timeout=5)
            if order_resp.status_code == 200:
                order_data = order_resp.json()
                items = [{'book_id': i['book_id'], 'quantity': i['quantity']} for i in order_data.get('items', [])]
                requests.post(f"{INVENTORY_SERVICE_URL}/inventory/release/", json={"items": items}, timeout=5)
            
            requests.put(
                f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                json={"status": "cancelled"}, timeout=5
            )
        except requests.exceptions.RequestException:
            pass
        
        return Response({
            "message": "Payment refunded",
            "payment": PaymentSerializer(payment).data,
        })
