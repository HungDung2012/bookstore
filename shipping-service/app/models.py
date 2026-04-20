from django.db import models


class Shipment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PACKED = "packed"
    STATUS_SHIPPING = "shipping"
    STATUS_DELIVERED = "delivered"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PACKED, "Packed"),
        (STATUS_SHIPPING, "Shipping"),
        (STATUS_DELIVERED, "Delivered"),
    ]

    order_id = models.IntegerField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    tracking_code = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.tracking_code:
            self.tracking_code = f"SHP-{self.id:06d}"
            super().save(update_fields=["tracking_code"])

    def __str__(self):
        return f"Shipment #{self.id} for order #{self.order_id}"
