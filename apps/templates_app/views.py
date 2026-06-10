from rest_framework import mixins, viewsets
from rest_framework.permissions import AllowAny

from .models import ResumeTemplate
from .serializers import ResumeTemplateSerializer


class ResumeTemplateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = ResumeTemplateSerializer
    permission_classes = [AllowAny]
    queryset = ResumeTemplate.objects.filter(is_active=True)
