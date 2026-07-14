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
        class_rep = User(username="classrep", role=User.RoleChoices.CLASS_REP)

        self.assertTrue(admin.is_admin())
        self.assertTrue(teacher.is_teacher())
        self.assertTrue(class_rep.is_class_rep())
        self.assertFalse(admin.is_teacher())
        self.assertFalse(teacher.is_admin())
        self.assertFalse(class_rep.is_admin())


class ClassRepCreateViewTests(TestCase):
    def setUp(self):
        from core.models import Department, Semester
        from academics.models import Section
        from core.testing import get_test_school

        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.school = get_test_school(code="acct-f26cr")
        self.admin.school = self.school
        self.admin.save(update_fields=['school'])
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26CR",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.section = Section.objects.create(
            name="10A",
            year=1,
            section_label="A",
            semester=self.semester,
            department=self.department,
        )
        self.url = reverse("accounts:class_rep_create")
        self.valid_payload = {
            "username": "classrep1",
            "email": "classrep1@example.com",
            "first_name": "Class",
            "last_name": "Rep",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
            "section": self.section.pk,
        }

    def test_admin_can_create_class_rep(self):
        from academics.models import ClassRepProfile

        self.client.login(username="admin", password="password")
        response = self.client.post(self.url, self.valid_payload)

        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="classrep1")
        self.assertEqual(user.role, User.RoleChoices.CLASS_REP)
        self.assertTrue(user.is_class_rep())
        profile = ClassRepProfile.objects.get(user=user)
        self.assertEqual(profile.section, self.section)

    def test_teacher_cannot_create_class_rep(self):
        User.objects.create_user(
            username="teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.client.login(username="teacher", password="password")
        response = self.client.post(self.url, self.valid_payload)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(User.objects.filter(username="classrep1").exists())


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
