from rest_framework import serializers

from .models import LEVELS, SKILLS


class StartAttemptSerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=LEVELS)
    skill = serializers.ChoiceField(choices=SKILLS)
    mock_test = serializers.IntegerField(min_value=1, max_value=20)
    mode = serializers.ChoiceField(choices=["practice", "mock"], default="practice")


class AnswerSerializer(serializers.Serializer):
    choice = serializers.IntegerField(min_value=0, max_value=2, required=False)
    text = serializers.CharField(max_length=10000, required=False, allow_blank=True)
    spoken = serializers.BooleanField(required=False)
    used_transcript = serializers.BooleanField(default=False)


class PlaybackSerializer(serializers.Serializer):
    failed = serializers.BooleanField(default=False)
