from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = [
        ('order_confirmed', 'Order Confirmed'),
        ('order_paid', 'Order Paid'),
        ('order_shipped', 'Order Shipped'),
        ('order_delivered', 'Order Delivered'),
        ('order_cancelled', 'Order Cancelled'),
        ('payment_success', 'Payment Successful'),
        ('payment_failed', 'Payment Failed'),
        ('payment_refunded', 'Payment Refunded'),
        ('promotion', 'Promotion'),
        ('system', 'System'),
    ]
    user_id = models.IntegerField(db_index=True)
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    reference_id = models.IntegerField(null=True, blank=True)  # order_id, payment_id, etc.
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] {self.title} → User#{self.user_id}"
