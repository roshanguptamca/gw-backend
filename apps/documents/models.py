from django.db import models
from django.contrib.auth.models import User
class Document(models.Model):
    owner=models.ForeignKey(User,on_delete=models.CASCADE)
    file=models.FileField(upload_to="documents/")
    original_name=models.CharField(max_length=255)
    created_at=models.DateTimeField(auto_now_add=True)