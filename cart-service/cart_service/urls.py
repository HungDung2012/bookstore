from django.contrib import admin
from django.urls import path
from app.views import CartCreate, AddCartItem, ViewCart, UpdateCartItem, DeleteCartItem

urlpatterns = [
    path('admin/', admin.site.urls),
    path('carts/', CartCreate.as_view()),
    path('cart-items/', AddCartItem.as_view()),
    path('carts/<int:customer_id>/', ViewCart.as_view()),
    path('carts/<int:customer_id>/update-item/', UpdateCartItem.as_view()),
    path('carts/<int:customer_id>/delete-item/<int:item_id>/', DeleteCartItem.as_view()),
]
