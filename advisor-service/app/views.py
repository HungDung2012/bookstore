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
        payload = AdvisorService().chat(
            user_id=serializer.validated_data.get("user_id"),
            question=serializer.validated_data["question"],
        )
        return Response(payload, status=status.HTTP_200_OK)


class AdvisorProfileView(APIView):
    def get(self, request, user_id):
        payload = AdvisorService().profile(user_id=user_id)
        return Response(payload, status=status.HTTP_200_OK)
