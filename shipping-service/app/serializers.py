from rest_framework import serializers

from .models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = ["id", "order_id", "status", "tracking_code", "created_at", "updated_at"]
        read_only_fields = ["id", "tracking_code", "created_at", "updated_at"]
