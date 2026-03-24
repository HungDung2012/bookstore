from django.contrib import admin
from django.urls import path
from app.views import CustomerListCreate, CustomerDetail, CustomerUpdateCart

urlpatterns = [
    path('admin/', admin.site.urls),
    path('customers/', CustomerListCreate.as_view()),
    path('customers/<int:pk>/', CustomerDetail.as_view()),
    path('customers/<int:pk>/update-cart/', CustomerUpdateCart.as_view()),
]
