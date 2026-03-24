from rest_framework import serializers
from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = OrderItem
        fields = ['id', 'book_id', 'book_title', 'quantity', 'unit_price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user_id', 'status', 'total_amount',
            'shipping_address', 'shipping_name', 'shipping_phone',
            'note', 'created_at', 'updated_at', 'items',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CheckoutSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    shipping_name = serializers.CharField(max_length=255)
    shipping_phone = serializers.CharField(max_length=20)
    shipping_address = serializers.CharField()
    note = serializers.CharField(required=False, default='', allow_blank=True)
    payment_method = serializers.ChoiceField(choices=['cod', 'bank_transfer', 'momo', 'vnpay'])
