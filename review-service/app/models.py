from django.db import models


class Review(models.Model):
    book_id = models.IntegerField()
    user_id = models.IntegerField()
    rating = models.IntegerField(choices=[(i, f"{i} star{'s' if i > 1 else ''}") for i in range(1, 6)])
    title = models.CharField(max_length=255, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('book_id', 'user_id')
        ordering = ['-created_at']

    def __str__(self):
        return f"Review by User#{self.user_id} for Book#{self.book_id} - {self.rating}⭐"
