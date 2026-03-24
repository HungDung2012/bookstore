from django.contrib import admin
from django.urls import path
from app.views import BookListCreate, BookDetail, CategoryList, PublisherList, UpdatePrice, AddPromotion

urlpatterns = [
    path('admin/', admin.site.urls),
    path('books/', BookListCreate.as_view()),
    path('books/<int:pk>/', BookDetail.as_view()),
    path('categories/', CategoryList.as_view()),
    path('publishers/', PublisherList.as_view()),
    path('books/<int:pk>/update-price/', UpdatePrice.as_view()),
    path('books/<int:pk>/add-promotion/', AddPromotion.as_view()),
]
