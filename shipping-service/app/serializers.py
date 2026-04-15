from rest_framework import serializers

from .models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    ALLOWED_STATUS_TRANSITIONS = {
        Shipment.STATUS_PENDING: {Shipment.STATUS_PACKED},
        Shipment.STATUS_PACKED: {Shipment.STATUS_SHIPPING},
        Shipment.STATUS_SHIPPING: {Shipment.STATUS_DELIVERED},
        Shipment.STATUS_DELIVERED: set(),
    }

    class Meta:
        model = Shipment
        fields = ["id", "order_id", "status", "tracking_code", "created_at", "updated_at"]
        read_only_fields = ["id", "tracking_code", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance:
            requested_order_id = attrs.get("order_id")
            if requested_order_id is not None and requested_order_id != self.instance.order_id:
                raise serializers.ValidationError({"order_id": "order_id cannot be changed."})

            requested_status = attrs.get("status")
            current_status = self.instance.status
            if requested_status and requested_status != current_status:
                allowed_statuses = self.ALLOWED_STATUS_TRANSITIONS.get(current_status, set())
                if requested_status not in allowed_statuses:
                    raise serializers.ValidationError(
                        {"status": f"Invalid transition from '{current_status}' to '{requested_status}'."}
                    )

        return attrs
