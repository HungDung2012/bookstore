from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Notification
from .serializers import NotificationSerializer


class NotificationListCreate(APIView):
    """GET /notifications/?user_id=X — Lấy thông báo theo user
       GET /notifications/?user_id=X&unread=true — Chỉ thông báo chưa đọc
       POST /notifications/ — Tạo thông báo mới (gọi bởi các service khác)"""
    def get(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)

        notifications = Notification.objects.filter(user_id=user_id)
        
        unread_only = request.query_params.get('unread', '').lower()
        if unread_only in ('true', '1', 'yes'):
            notifications = notifications.filter(is_read=False)
        
        return Response(NotificationSerializer(notifications, many=True).data)

    def post(self, request):
        serializer = NotificationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class NotificationDetailView(APIView):
    """GET /notifications/<id>/ — Chi tiết thông báo"""
    def get(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk)
        return Response(NotificationSerializer(notification).data)


class MarkReadView(APIView):
    """POST /notifications/<id>/read/ — Đánh dấu đã đọc"""
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk)
        notification.is_read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    """POST /notifications/mark-all-read/?user_id=X — Đánh dấu tất cả đã đọc"""
    def post(self, request):
        user_id = request.data.get('user_id') or request.query_params.get('user_id')
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        count = Notification.objects.filter(user_id=user_id, is_read=False).update(is_read=True)
        return Response({"message": f"Marked {count} notifications as read"})


class UnreadCountView(APIView):
    """GET /notifications/unread-count/?user_id=X — Số thông báo chưa đọc"""
    def get(self, request):
        user_id = request.query_params.get('user_id')
        if not user_id:
            return Response({"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        count = Notification.objects.filter(user_id=user_id, is_read=False).count()
        return Response({"user_id": int(user_id), "unread_count": count})
