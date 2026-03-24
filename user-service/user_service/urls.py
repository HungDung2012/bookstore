from django.contrib import admin
from django.urls import path
from app.views import (
    RegisterView, LoginView, ProfileView,
    VerifyTokenView, UserListView, UserDetailView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('auth/register/', RegisterView.as_view()),
    path('auth/login/', LoginView.as_view()),
    path('auth/profile/', ProfileView.as_view()),
    path('auth/verify/', VerifyTokenView.as_view()),
    path('users/', UserListView.as_view()),
    path('users/<int:pk>/', UserDetailView.as_view()),
]
