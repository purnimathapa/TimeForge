import os
import django
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.contrib.auth import get_user_model

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'timeforge.settings')
django.setup()

User = get_user_model()
user = User.objects.first()

client = Client()
if user:
    client.force_login(user)

def measure_view(url_name, *args, **kwargs):
    url = reverse(url_name, args=args, kwargs=kwargs)
    with CaptureQueriesContext(connection) as queries:
        response = client.get(url, HTTP_HOST='localhost')
    
    print(f"URL: {url} | Status: {response.status_code}")
    print(f"Queries: {len(queries)}")
    for q in queries:
        print(q['sql'])
    return len(queries)

# Need to find an active timetable.
from timetable.models import Timetable
from scheduling.models import Semester

timetable = Timetable.objects.first()

if timetable:
    print(f"Measuring teacher view for timetable {timetable.id}")
    measure_view('timetable:teacher_view')
else:
    print("No timetable found.")
