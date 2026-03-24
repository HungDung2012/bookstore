from django.contrib import admin
from django.urls import path
from app.views import OrderListView, OrderDetailView, CheckoutView, UpdateOrderStatusView, CancelOrderView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('orders/', OrderListView.as_view()),
    path('orders/<int:pk>/', OrderDetailView.as_view()),
    path('orders/checkout/', CheckoutView.as_view()),
    path('orders/<int:pk>/status/', UpdateOrderStatusView.as_view()),
    path('orders/<int:pk>/cancel/', CancelOrderView.as_view()),
]
