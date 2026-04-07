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


class PaymentListCreate(APIView):
    def get(self, request):
        order_id = request.query_params.get("order_id")
        if order_id:
            payments = Payment.objects.filter(order_id=order_id)
        else:
            payments = Payment.objects.all().order_by("-created_at")
        return Response(PaymentSerializer(payments, many=True).data)

    def post(self, request):
        serializer = PaymentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        existing = Payment.objects.filter(order_id=data["order_id"]).first()
        if existing:
            return Response(PaymentSerializer(existing).data)

        payment = Payment.objects.create(**data)
        if data["method"] == "cod":
            payment.status = "completed"
            payment.save(update_fields=["status", "updated_at"])

        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    def get(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        return Response(PaymentSerializer(payment).data)


class ProcessPaymentView(APIView):
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        if payment.status != "pending":
            return Response(
                {"error": f"Payment is already '{payment.status}'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        success = request.data.get("success", True)
        if success:
            payment.status = "completed"
            payment.save(update_fields=["status", "updated_at"])
            try:
                requests.put(
                    f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                    json={"status": "paid"},
                    timeout=5,
                )
            except requests.exceptions.RequestException:
                pass
            return Response(
                {
                    "message": "Payment successful",
                    "payment": PaymentSerializer(payment).data,
                }
            )

        payment.status = "failed"
        payment.save(update_fields=["status", "updated_at"])
        try:
            requests.put(
                f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                json={"status": "cancelled"},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass

        return Response(
            {
                "message": "Payment failed",
                "payment": PaymentSerializer(payment).data,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )


class RefundView(APIView):
    def post(self, request, pk):
        payment = get_object_or_404(Payment, pk=pk)
        if payment.status != "completed":
            return Response(
                {"error": "Can only refund completed payments"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment.status = "refunded"
        payment.save(update_fields=["status", "updated_at"])
        try:
            requests.put(
                f"{ORDER_SERVICE_URL}/orders/{payment.order_id}/status/",
                json={"status": "cancelled"},
                timeout=5,
            )
        except requests.exceptions.RequestException:
            pass

        return Response(
            {
                "message": "Payment refunded",
                "payment": PaymentSerializer(payment).data,
            }
        )
