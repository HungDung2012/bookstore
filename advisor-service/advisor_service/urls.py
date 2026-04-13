from django.contrib import admin
from django.urls import path

from app.views import AdvisorChatView, health_check


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", health_check),
    path("advisor/chat/", AdvisorChatView.as_view()),
]
