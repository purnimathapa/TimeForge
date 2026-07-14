from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from core.models import Department, Semester
from core.testing import get_test_school
from timetable.models import Timetable


class AdminDashboardTimetableStateTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.school = get_test_school(code="dash-f26")
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )

    def test_admin_dashboard_shows_empty_state_without_timetable(self):
        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_timetable"])
        self.assertContains(response, "No Timetable Generated Yet")

    def test_admin_dashboard_shows_timetable_summary_when_present(self):
        timetable = Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.DRAFT,
            penalty_score=12,
        )

        self.client.login(username="admin", password="password")
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_timetable"])
        self.assertEqual(response.context["latest_timetable"], timetable)
        self.assertContains(response, f"v{timetable.version}")
        self.assertContains(response, "Draft")
        self.assertNotContains(response, "No Timetable Generated Yet")


class TeacherDashboardPublishedOnlyTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.school = get_test_school(code="dash-f26t")
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26T",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        Department.objects.create(name="Computer Science", code="CS", school=self.school)

    def test_teacher_dashboard_ignores_draft_timetable(self):
        Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.DRAFT,
        )

        self.client.login(username="teacher", password="password")
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_timetable"])
        self.assertContains(response, "No Timetable Available")

    def test_teacher_dashboard_detects_published_timetable(self):
        Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.PUBLISHED,
        )

        self.client.login(username="teacher", password="password")
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_timetable"])
        self.assertContains(response, "Your Timetable is Ready")
