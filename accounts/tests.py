from django.test import TestCase

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
