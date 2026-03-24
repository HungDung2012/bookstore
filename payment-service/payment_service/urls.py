from django.contrib import admin
from django.urls import path
from app.views import PaymentListCreate, PaymentDetailView, ProcessPaymentView, RefundView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('payments/', PaymentListCreate.as_view()),
    path('payments/<int:pk>/', PaymentDetailView.as_view()),
    path('payments/<int:pk>/process/', ProcessPaymentView.as_view()),
    path('payments/<int:pk>/refund/', RefundView.as_view()),
]
