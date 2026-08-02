"""
academics/tests.py — model and view tests for the academics app.

Covers TeacherPortalView (availability formset update), model constraints, and
ClassRep profile behaviour. Standard admin CRUD views (Subject/Course/Teacher list
create update delete) are not smoke-tested here; tenant list isolation for
academics models is covered in core.tests.test_tenant_isolation.

Run:
  python manage.py test academics.tests
"""

from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse

from academics.models import Course, Subject, TeacherProfile, ClassRepProfile
from accounts.models import User
from core.models import Department, Session
from core.testing import get_test_school
from scheduling.models import TeacherAvailability, TimeSlot


class TeacherPortalViewTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="portal_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="PT001",
        )
        TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )

    def test_teacher_portal_resolves_teacher_profile(self):
        self.client.login(username="portal_teacher", password="password")
        response = self.client.get(reverse("academics:teacher_portal"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["teacher"], self.teacher)
        self.assertIn("formset", response.context)
        self.assertEqual(
            TeacherAvailability.objects.filter(teacher=self.teacher).count(),
            1,
        )


class AcademicsModelTests(TestCase):
    def setUp(self):
        self.school = get_test_school(code="acad-f26")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.user = User.objects.create_user(
            username="teacher1",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)

    def test_subject_creation(self):
        subject = Subject.objects.create(
            name="Mathematics",
            code="MATH101",
            lecture_hours_per_week=5,
        )
        subject.departments.add(self.department)
        self.assertEqual(subject.name, "Mathematics")
        self.assertEqual(subject.code, "MATH101")
        self.assertIn(self.department, subject.departments.all())

    def test_course_unique_code_per_department(self):
        Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )

        with self.assertRaises(IntegrityError):
            Course.objects.create(
                name="BE Computer Engineering Duplicate",
                code="BE-CE",
                department=self.department,
            )

    def test_course_save_creates_levels(self):
        course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        levels = list(course.levels.order_by("level").values_list("level", flat=True))
        self.assertEqual(levels, list(range(1, 9)))

    def test_teacher_profile_creation(self):
        teacher = TeacherProfile.objects.create(
            user=self.user, employee_id="T123", title=TeacherProfile.Title.DR,
        )
        self.assertEqual(teacher.employee_id, "T123")
        # The string shows the ranked name, not the employee number.
        self.assertIn(teacher.display_name, str(teacher))
        self.assertIn("Dr.", str(teacher))
        self.assertNotIn("T123", str(teacher))

    def test_generate_employee_id_sequences(self):
        self.assertEqual(TeacherProfile.generate_employee_id(), "EMP-0001")
        TeacherProfile.objects.create(user=self.user, employee_id="EMP-0001")
        other = User.objects.create_user(
            username="teacher2",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.assertEqual(TeacherProfile.generate_employee_id(), "EMP-0002")
        TeacherProfile.objects.create(user=other, employee_id="EMP-0007")
        self.assertEqual(TeacherProfile.generate_employee_id(), "EMP-0008")


class ClassRepProfileTests(TestCase):
    def setUp(self):
        self.school = get_test_school(code="acad-f26cr")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.user = User.objects.create_user(
            username="classrep",
            password="password",
            role=User.RoleChoices.CLASS_REP,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course_level = self.course.levels.get(level=1)

    def test_class_rep_profile_links_user_to_course_level(self):
        profile = ClassRepProfile.objects.create(user=self.user, course_level=self.course_level)
        self.assertEqual(profile.user, self.user)
        self.assertEqual(profile.course_level, self.course_level)
        self.assertIn("BE-CE", str(profile))
