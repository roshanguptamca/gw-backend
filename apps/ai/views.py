from rest_framework.decorators import api_view
from rest_framework.response import Response
@api_view(["POST"])
def explain(request):
    return Response({"explanation":"Simple explanation","disclaimer":"Not legal advice"})