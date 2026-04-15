from rest_framework import serializers


class AdvisorChatSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False, allow_null=True)
    question = serializers.CharField()
