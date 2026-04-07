from collections import defaultdict

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InventoryItem
from .serializers import InventoryItemSerializer


def _aggregate_items(items):
    aggregated = defaultdict(int)
    for item in items:
        book_id = item.get("book_id")
        quantity = item.get("quantity", 1)
        if book_id is None:
            continue
        aggregated[int(book_id)] += int(quantity)
    return aggregated


class InventoryListCreate(APIView):
    def get(self, request):
        items = InventoryItem.objects.all()
        serializer = InventoryItemSerializer(items, many=True)
        return Response(serializer.data)

    def post(self, request):
        serializer = InventoryItemSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class InventoryDetail(APIView):
    def get(self, request, book_id):
        item = get_object_or_404(InventoryItem, book_id=book_id)
        return Response(InventoryItemSerializer(item).data)

    def put(self, request, book_id):
        item = get_object_or_404(InventoryItem, book_id=book_id)
        serializer = InventoryItemSerializer(item, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CheckStock(APIView):
    def post(self, request):
        aggregated = _aggregate_items(request.data.get("items", []))
        details = []
        all_available = True

        for book_id, quantity in aggregated.items():
            try:
                inventory = InventoryItem.objects.get(book_id=book_id)
                sufficient = inventory.available >= quantity
                details.append(
                    {
                        "book_id": book_id,
                        "requested": quantity,
                        "available": inventory.available,
                        "sufficient": sufficient,
                    }
                )
                if not sufficient:
                    all_available = False
            except InventoryItem.DoesNotExist:
                details.append(
                    {
                        "book_id": book_id,
                        "requested": quantity,
                        "available": 0,
                        "sufficient": False,
                    }
                )
                all_available = False

        return Response({"all_available": all_available, "details": details})


class ReserveStock(APIView):
    @transaction.atomic
    def post(self, request):
        aggregated = _aggregate_items(request.data.get("items", []))
        locked_items = {}

        for book_id, quantity in aggregated.items():
            try:
                inventory = InventoryItem.objects.select_for_update().get(book_id=book_id)
            except InventoryItem.DoesNotExist:
                return Response(
                    {"error": f"Inventory not found for book {book_id}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if inventory.available < quantity:
                return Response(
                    {"error": f"Insufficient stock for book {book_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            locked_items[book_id] = inventory

        for book_id, quantity in aggregated.items():
            inventory = locked_items[book_id]
            inventory.reserved += quantity
            inventory.save(update_fields=["reserved", "updated_at"])

        return Response(
            {
                "message": "Stock reserved",
                "items": [{"book_id": book_id, "reserved": quantity} for book_id, quantity in aggregated.items()],
            }
        )


class ConfirmDeduction(APIView):
    @transaction.atomic
    def post(self, request):
        aggregated = _aggregate_items(request.data.get("items", []))
        locked_items = {}

        for book_id, quantity in aggregated.items():
            try:
                inventory = InventoryItem.objects.select_for_update().get(book_id=book_id)
            except InventoryItem.DoesNotExist:
                return Response(
                    {"error": f"Inventory not found for book {book_id}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            if inventory.quantity < quantity or inventory.reserved < quantity:
                return Response(
                    {"error": f"Cannot confirm stock for book {book_id}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            locked_items[book_id] = inventory

        for book_id, quantity in aggregated.items():
            inventory = locked_items[book_id]
            inventory.quantity -= quantity
            inventory.reserved -= quantity
            inventory.save(update_fields=["quantity", "reserved", "updated_at"])

        return Response({"message": "Stock deducted successfully"})


class ReleaseStock(APIView):
    @transaction.atomic
    def post(self, request):
        aggregated = _aggregate_items(request.data.get("items", []))
        for book_id, quantity in aggregated.items():
            inventory = InventoryItem.objects.select_for_update().filter(book_id=book_id).first()
            if not inventory:
                continue
            inventory.reserved = max(0, inventory.reserved - quantity)
            inventory.save(update_fields=["reserved", "updated_at"])
        return Response({"message": "Stock released"})


class RestockInventory(APIView):
    @transaction.atomic
    def post(self, request):
        aggregated = _aggregate_items(request.data.get("items", []))
        for book_id, quantity in aggregated.items():
            try:
                inventory = InventoryItem.objects.select_for_update().get(book_id=book_id)
            except InventoryItem.DoesNotExist:
                return Response(
                    {"error": f"Inventory not found for book {book_id}"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            inventory.quantity += quantity
            inventory.save(update_fields=["quantity", "updated_at"])

        return Response({"message": "Inventory restocked"})
