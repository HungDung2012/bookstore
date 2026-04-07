from django.contrib import admin
from django.urls import path
from app.views import (
    CheckStock,
    ConfirmDeduction,
    InventoryDetail,
    InventoryListCreate,
    ReleaseStock,
    ReserveStock,
    RestockInventory,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('inventory/', InventoryListCreate.as_view()),
    path('inventory/<int:book_id>/', InventoryDetail.as_view()),
    path('inventory/check-stock/', CheckStock.as_view()),
    path('inventory/reserve/', ReserveStock.as_view()),
    path('inventory/confirm/', ConfirmDeduction.as_view()),
    path('inventory/release/', ReleaseStock.as_view()),
    path('inventory/restock/', RestockInventory.as_view()),
]
