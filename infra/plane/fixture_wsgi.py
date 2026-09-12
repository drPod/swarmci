"""A private Django fixture endpoint served by Plane's existing Gunicorn runtime."""
import json
import os
import secrets
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plane.settings.production')
import django

django.setup()
from django.conf import settings
from django.core.wsgi import get_wsgi_application
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from seed import operate

settings.ROOT_URLCONF = __name__
# This fixture endpoint uses its own bearer authentication, not app sessions.
settings.MIDDLEWARE = []

@csrf_exempt
def sessions(request):
    token = Path('/run/secrets/swarm-fixture-token').read_text().strip()
    if not secrets.compare_digest(request.headers.get('Authorization', ''), 'Bearer '+token):
        return JsonResponse({'detail':'Invalid fixture token'},status=401)
    if request.method != 'POST':
        return JsonResponse({'detail':'POST required'},status=405)
    try:
        import re
        data=json.loads(request.body)
        if data.get('operation') not in ('create','snapshot','delete'):
            raise ValueError('Unknown fixture operation')
        if data['operation'] != 'create' and not re.fullmatch('[a-f0-9]{16}',data.get('id','')):
            raise ValueError('Invalid fixture session ID')
        return JsonResponse(operate(data))
    except (ValueError,TypeError,json.JSONDecodeError):
        return JsonResponse({'detail':'Invalid fixture request'},status=422)

urlpatterns=[path('sessions',sessions)]
application=get_wsgi_application()
