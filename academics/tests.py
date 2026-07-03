from django.db.utils import IntegrityError
from django.test import TestCase

from academics.models import Section, Subject, TeacherProfile
from accounts.models import User
from core.models import Semester, Department


class AcademicsModelTests(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(name="Fall 2026", code="F26", start_date="2026-08-01", end_date="2026-12-15", is_active=True)
        self.user = User.objects.create_user(username="teacher1", password="password", role=User.RoleChoices.TEACHER)
        self.department = Department.objects.create(name="Computer Science", code="CS")

    def test_subject_creation(self):
        subject = Subject.objects.create(name="Mathematics", code="MATH101", lecture_hours_per_week=5, department=self.department)
        self.assertEqual(subject.name, "Mathematics")
        self.assertEqual(subject.code, "MATH101")

    def test_section_unique_per_semester(self):
        Section.objects.create(name="10A", year=1, section_label="A", semester=self.semester, department=self.department)
        
        with self.assertRaises(IntegrityError):
            Section.objects.create(name="10A", year=1, section_label="A", semester=self.semester, department=self.department)

    def test_teacher_profile_creation(self):
        teacher = TeacherProfile.objects.create(user=self.user, employee_id="T123")
        self.assertEqual(teacher.employee_id, "T123")
        self.assertIn("T123", str(teacher))
