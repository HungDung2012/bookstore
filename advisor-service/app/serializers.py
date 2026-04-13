from rest_framework import serializers


class AdvisorChatSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    question = serializers.CharField()
