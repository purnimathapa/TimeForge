from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class UserModelTests(TestCase):
    def test_user_creation(self):
        """Test creating a regular user."""
        user = User.objects.create_user(username="testuser", password="password", role=User.RoleChoices.TEACHER)
        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.role, User.RoleChoices.TEACHER)
        self.assertTrue(user.is_teacher())
        self.assertFalse(user.is_admin())

    def test_admin_creation(self):
        """Test creating a superuser/admin."""
        admin = User.objects.create_superuser(username="admin", password="password")
        self.assertEqual(admin.role, User.RoleChoices.ADMIN) # Default is ADMIN
        self.assertTrue(admin.is_admin())
        self.assertFalse(admin.is_teacher())

    def test_role_methods(self):
        """Test the role helper methods."""
        admin = User(username="admin", role=User.RoleChoices.ADMIN)
        teacher = User(username="teacher", role=User.RoleChoices.TEACHER)

        self.assertTrue(admin.is_admin())
        self.assertTrue(teacher.is_teacher())
        self.assertFalse(admin.is_teacher())
        self.assertFalse(teacher.is_admin())


class AdminCreateViewTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher = User.objects.create_user(
            username="teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.url = reverse("accounts:admin_create")
        self.valid_payload = {
            "username": "newadmin",
            "email": "newadmin@example.com",
            "first_name": "New",
            "last_name": "Admin",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
        }

    def test_admin_can_get_create_form(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_admin_can_create_admin_account(self):
        self.client.login(username="admin", password="password")
        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        new_user = User.objects.get(username="newadmin")
        self.assertEqual(new_user.role, User.RoleChoices.ADMIN)
        self.assertTrue(new_user.is_admin())

    def test_teacher_cannot_get_create_form(self):
        self.client.login(username="teacher", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_create_admin_account(self):
        self.client.login(username="teacher", password="password")
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="newadmin").exists())
