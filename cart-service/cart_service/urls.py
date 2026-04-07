from django.contrib import admin
from django.urls import path

from app.views import AddCartItem, CartCreate, ClearCart, DeleteCartItem, UpdateCartItem, ViewCart

urlpatterns = [
    path('admin/', admin.site.urls),
    path('carts/', CartCreate.as_view()),
    path('cart-items/', AddCartItem.as_view()),
    path('carts/<int:customer_id>/', ViewCart.as_view()),
    path('carts/<int:customer_id>/clear/', ClearCart.as_view()),
    path('carts/<int:customer_id>/update-item/', UpdateCartItem.as_view()),
    path('carts/<int:customer_id>/delete-item/<int:item_id>/', DeleteCartItem.as_view()),
]
