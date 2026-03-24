from django.contrib import admin
from django.urls import path
from app.views import (
    NotificationListCreate, NotificationDetailView,
    MarkReadView, MarkAllReadView, UnreadCountView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('notifications/', NotificationListCreate.as_view()),
    path('notifications/<int:pk>/', NotificationDetailView.as_view()),
    path('notifications/<int:pk>/read/', MarkReadView.as_view()),
    path('notifications/mark-all-read/', MarkAllReadView.as_view()),
    path('notifications/unread-count/', UnreadCountView.as_view()),
]
