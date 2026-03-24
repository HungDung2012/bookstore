from django.contrib import admin
from django.urls import path
from app.views import ReviewListCreate, ReviewDetailView, BookRatingView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('reviews/', ReviewListCreate.as_view()),
    path('reviews/<int:pk>/', ReviewDetailView.as_view()),
    path('reviews/rating/<int:book_id>/', BookRatingView.as_view()),
]
