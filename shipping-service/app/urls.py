from django.urls import path

from .views import ShipmentDetailView, ShipmentListCreateView


urlpatterns = [
    path("shipping/", ShipmentListCreateView.as_view()),
    path("shipping/<int:pk>/", ShipmentDetailView.as_view()),
]
