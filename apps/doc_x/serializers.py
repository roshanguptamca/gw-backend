# app/serializers.py
from rest_framework import serializers
from .models import Document, Conversation

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 's3_key', 'content', 'summary', 'created_at']


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = ['id', 'document', 'role', 'message', 'created_at']
