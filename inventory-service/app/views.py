from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import InventoryItem
from .serializers import InventoryItemSerializer


class InventoryListCreate(APIView):
    """GET /inventory/ — Danh sách tồn kho
       POST /inventory/ — Tạo mới tồn kho cho 1 cuốn sách"""
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
    """GET /inventory/<book_id>/ — Xem tồn kho theo book_id
       PUT /inventory/<book_id>/ — Cập nhật tồn kho"""
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
    """POST /inventory/check-stock/ — Kiểm tra xem có đủ hàng không
       Body: {"items": [{"book_id": 1, "quantity": 2}, ...]}"""
    def post(self, request):
        items = request.data.get("items", [])
        result = []
        all_available = True
        for item in items:
            book_id = item.get("book_id")
            qty = item.get("quantity", 1)
            try:
                inv = InventoryItem.objects.get(book_id=book_id)
                available = inv.available >= qty
                result.append({
                    "book_id": book_id,
                    "requested": qty,
                    "available": inv.available,
                    "sufficient": available,
                })
                if not available:
                    all_available = False
            except InventoryItem.DoesNotExist:
                result.append({
                    "book_id": book_id,
                    "requested": qty,
                    "available": 0,
                    "sufficient": False,
                })
                all_available = False
        return Response({"all_available": all_available, "details": result})


class ReserveStock(APIView):
    """POST /inventory/reserve/ — Giữ hàng cho đơn hàng đang pending
       Body: {"items": [{"book_id": 1, "quantity": 2}, ...]}"""
    @transaction.atomic
    def post(self, request):
        items = request.data.get("items", [])
        reserved_items = []
        for item in items:
            book_id = item.get("book_id")
            qty = item.get("quantity", 1)
            try:
                inv = InventoryItem.objects.select_for_update().get(book_id=book_id)
                if inv.available >= qty:
                    inv.reserved += qty
                    inv.save()
                    reserved_items.append({"book_id": book_id, "reserved": qty})
                else:
                    # Rollback all reservations
                    return Response(
                        {"error": f"Insufficient stock for book {book_id}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except InventoryItem.DoesNotExist:
                return Response(
                    {"error": f"Inventory not found for book {book_id}"},
                    status=status.HTTP_404_NOT_FOUND
                )
        return Response({"message": "Stock reserved", "items": reserved_items})


class ConfirmDeduction(APIView):
    """POST /inventory/confirm/ — Xác nhận trừ kho (sau khi thanh toán thành công)
       Body: {"items": [{"book_id": 1, "quantity": 2}, ...]}"""
    @transaction.atomic
    def post(self, request):
        items = request.data.get("items", [])
        for item in items:
            book_id = item.get("book_id")
            qty = item.get("quantity", 1)
            try:
                inv = InventoryItem.objects.select_for_update().get(book_id=book_id)
                inv.quantity -= qty
                inv.reserved -= qty
                inv.save()
            except InventoryItem.DoesNotExist:
                return Response(
                    {"error": f"Inventory not found for book {book_id}"},
                    status=status.HTTP_404_NOT_FOUND
                )
        return Response({"message": "Stock deducted successfully"})


class ReleaseStock(APIView):
    """POST /inventory/release/ — Hủy giữ hàng (khi thanh toán thất bại hoặc hủy đơn)
       Body: {"items": [{"book_id": 1, "quantity": 2}, ...]}"""
    @transaction.atomic
    def post(self, request):
        items = request.data.get("items", [])
        for item in items:
            book_id = item.get("book_id")
            qty = item.get("quantity", 1)
            try:
                inv = InventoryItem.objects.select_for_update().get(book_id=book_id)
                inv.reserved = max(0, inv.reserved - qty)
                inv.save()
            except InventoryItem.DoesNotExist:
                pass  # Silent fail for release
        return Response({"message": "Stock released"})
