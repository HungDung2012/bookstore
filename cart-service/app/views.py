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

class CartCreate(APIView):
    def post(self, request):
        serializer = CartSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

class AddCartItem(APIView):
    def post(self, request):
        book_id = request.data.get("book_id")
        cart_id = request.data.get("cart")
        
        # Check if item already exists in cart, if so just update quantity
        try:
            cart = Cart.objects.get(id=cart_id)
            existing = CartItem.objects.filter(cart=cart, book_id=book_id).first()
            if existing:
                qty = int(request.data.get("quantity", 1))
                existing.quantity += qty
                existing.save()
                return Response(CartItemSerializer(existing).data)
        except Cart.DoesNotExist:
            pass
        
        try:
            r = requests.get(f"{BOOK_SERVICE_URL}/books/", timeout=5)
            r.raise_for_status()
            books = r.json()
            if not any(b["id"] == int(book_id) for b in books):
                return Response({"error": "Book not found"}, status=404)
        except requests.exceptions.RequestException as e:
            return Response({"error": f"Error contacting book-service: {str(e)}"}, status=500)

        serializer = CartItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors)

class ViewCart(APIView):
    def get(self, request, customer_id):
        try:
            cart = Cart.objects.get(customer_id=customer_id)
        except Cart.DoesNotExist:
            return Response({"error": "Cart not found"}, status=404)
        
        items = CartItem.objects.filter(cart=cart)
        serializer = CartItemSerializer(items, many=True)
        return Response(serializer.data)

class UpdateCartItem(APIView):
    def put(self, request, customer_id):
        try:
            cart = Cart.objects.get(customer_id=customer_id)
        except Cart.DoesNotExist:
            return Response({"error": "Cart not found"}, status=404)
        
        book_id = request.data.get("book_id")
        quantity = request.data.get("quantity")
        
        if not book_id or quantity is None:
            return Response({"error": "book_id and quantity are required"}, status=400)
            
        try:
            cart_item = CartItem.objects.get(cart=cart, book_id=book_id)
            if int(quantity) <= 0:
                cart_item.delete()
                return Response({"message": "Item removed from cart"})
            else:
                cart_item.quantity = quantity
                cart_item.save()
                return Response(CartItemSerializer(cart_item).data)
        except CartItem.DoesNotExist:
            return Response({"error": "Item not found in cart"}, status=404)

class DeleteCartItem(APIView):
    def delete(self, request, customer_id, item_id):
        try:
            cart = Cart.objects.get(customer_id=customer_id)
        except Cart.DoesNotExist:
            return Response({"error": "Cart not found"}, status=404)
        
        try:
            cart_item = CartItem.objects.get(id=item_id, cart=cart)
            cart_item.delete()
            return Response({"message": "Item deleted"}, status=status.HTTP_204_NO_CONTENT)
        except CartItem.DoesNotExist:
            return Response({"error": "Item not found"}, status=404)
