from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Shipment
from .serializers import ShipmentSerializer


class ShipmentListCreateView(APIView):
    def get(self, request):
        order_id = request.query_params.get("order_id")
        shipments = Shipment.objects.all().order_by("-created_at")
        if order_id:
            shipments = shipments.filter(order_id=order_id)
        return Response(ShipmentSerializer(shipments, many=True).data)

    def post(self, request):
        order_id = request.data.get("order_id")
        if order_id is not None:
            existing = Shipment.objects.filter(order_id=order_id).first()
            if existing:
                return Response(ShipmentSerializer(existing).data)

        serializer = ShipmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        shipment = serializer.save()
        return Response(ShipmentSerializer(shipment).data, status=status.HTTP_201_CREATED)


class ShipmentDetailView(APIView):
    def get(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)
        return Response(ShipmentSerializer(shipment).data)

    def patch(self, request, pk):
        shipment = get_object_or_404(Shipment, pk=pk)
        serializer = ShipmentSerializer(shipment, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return Response(serializer.data)
