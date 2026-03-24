from django.db import models


class InventoryItem(models.Model):
    book_id = models.IntegerField(unique=True)
    quantity = models.IntegerField(default=0)
    reserved = models.IntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def available(self):
        return self.quantity - self.reserved

    def __str__(self):
        return f"Book #{self.book_id}: qty={self.quantity}, reserved={self.reserved}, available={self.available}"
