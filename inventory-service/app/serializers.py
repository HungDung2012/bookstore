from rest_framework import serializers
from .models import InventoryItem


class InventoryItemSerializer(serializers.ModelSerializer):
    available = serializers.ReadOnlyField()

    class Meta:
        model = InventoryItem
        fields = ['id', 'book_id', 'quantity', 'reserved', 'available', 'updated_at']
        read_only_fields = ['id', 'updated_at']
