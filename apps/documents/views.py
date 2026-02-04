from rest_framework.viewsets import ModelViewSet
from rest_framework.parsers import MultiPartParser
from .models import Document
from .serializers import DocumentSerializer
class DocumentViewSet(ModelViewSet):
    serializer_class=DocumentSerializer
    parser_classes=[MultiPartParser]
    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)
    def perform_create(self,serializer):
        serializer.save(owner=self.request.user, original_name=self.request.FILES["file"].name)