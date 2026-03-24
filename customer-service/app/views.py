import os

import requests
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Customer
from .serializers import CustomerSerializer


def _service_url(env_name, default):
    value = os.getenv(env_name, default).rstrip("/")
    if not value.startswith(("http://", "https://")):
        value = f"http://{value}"
    return value


CART_SERVICE_URL = _service_url("CART_SERVICE_URL", "cart-service:8000")

class CustomerListCreate(APIView):
    def get(self, request):
        customers = Customer.objects.all()
        serializer = CustomerSerializer(customers, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = CustomerSerializer(data=request.data)
        if serializer.is_valid():
            customer = serializer.save()
            # Call cart-service
            try:
                requests.post(
                    f"{CART_SERVICE_URL}/carts/",
                    json={"customer_id": customer.id},
                    timeout=5
                )
            except requests.exceptions.RequestException as e:
                print(f"Error calling cart-service: {e}")
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomerDetail(APIView):
    def get_object(self, pk):
        return get_object_or_404(Customer, pk=pk)
    
    # updateCustomer()
    def put(self, request, pk):
        customer = self.get_object(pk)
        serializer = CustomerSerializer(customer, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CustomerUpdateCart(APIView):
    # updateCart()
    def put(self, request, pk):
        customer = self.get_object(pk)
        # Assuming the payload is something like: {"book_id": 1, "quantity": 5}
        try:
            r = requests.put(
                f"{CART_SERVICE_URL}/carts/{customer.id}/update-item/",
                json=request.data,
                timeout=5
            )
            r.raise_for_status()
            return Response(r.json(), status=r.status_code)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Error updating cart via cart-service: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
