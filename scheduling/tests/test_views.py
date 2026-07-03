from django.test import TestCase
from django.urls import reverse
from accounts.models import User

class SchedulingViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher = User.objects.create_user(username="teacher", password="password", role=User.RoleChoices.TEACHER)
        self.timeslot_url = reverse('scheduling:timeslot_list')

    def test_timeslot_list_unauthenticated(self):
        """Unauthenticated users should be redirected to login."""
        response = self.client.get(self.timeslot_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_timeslot_list_teacher(self):
        """Teachers should receive a 403 Forbidden."""
        self.client.login(username="teacher", password="password")
        response = self.client.get(self.timeslot_url)
        self.assertEqual(response.status_code, 403)

    def test_timeslot_list_admin(self):
        """Admins can access the view."""
        self.client.login(username="admin", password="password")
        response = self.client.get(self.timeslot_url)
        self.assertEqual(response.status_code, 200)
