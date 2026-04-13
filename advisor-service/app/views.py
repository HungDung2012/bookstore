from django.http import JsonResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import AdvisorChatSerializer
from .services.advisor import AdvisorService


def health_check(request):
    return JsonResponse({"status": "ok", "service": "advisor-service"})


class AdvisorChatView(APIView):
    def post(self, request):
        serializer = AdvisorChatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = AdvisorService().chat(**serializer.validated_data)
        return Response(payload, status=status.HTTP_200_OK)
