from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from accounts.models import User
from core.models import Department, Room, School, Session
from core.testing import get_test_school


class SchoolModelTests(TestCase):
    def test_school_create(self):
        school = School.objects.create(name="Demo Academy", code="demo")
        self.assertEqual(school.name, "Demo Academy")
        self.assertTrue(school.is_active)


class SchoolBackfillSmokeTests(TestCase):
    """Verify tenant FKs are required and can be assigned via test helper."""

    def test_core_models_require_school(self):
        school = get_test_school()
        department = Department.objects.create(name="CS", code="CS", school=school)
        room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=school)
        session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            school=school,
        )

        self.assertEqual(department.school_id, school.id)
        self.assertEqual(room.school_id, school.id)
        self.assertEqual(session.school_id, school.id)

    def test_non_superuser_user_can_have_school(self):
        school = get_test_school()
        user = User.objects.create_user(
            username="tenant_admin",
            password="password",
            role=User.RoleChoices.ADMIN,
            school=school,
        )
        self.assertEqual(user.school_id, school.id)


class SessionModelTests(TestCase):
    def setUp(self):
        self.school = get_test_school()

    def test_single_active_session(self):
        """Only one session may be active per school at a time."""
        Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )

        with self.assertRaises(ValidationError):
            Session.objects.create(
                name="Spring 2027",
                start_date="2027-01-10",
                end_date="2027-05-20",
                is_active=True,
                school=self.school,
            )

    def test_deactivating_session(self):
        """Deactivating a session should leave zero active sessions."""
        session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        session.is_active = False
        session.save()
        self.assertFalse(Session.objects.filter(is_active=True, school=self.school).exists())


class RoomModelTests(TestCase):
    def setUp(self):
        self.school = get_test_school()

    def test_room_creation(self):
        """Room should be created successfully with valid data."""
        room = Room.objects.create(
            name="101A",
            capacity=30,
            room_type="LECTURE",
            school=self.school,
        )
        self.assertEqual(room.name, "101A")
        self.assertEqual(room.capacity, 30)
        self.assertEqual(room.school_id, self.school.id)

    def test_room_name_unique(self):
        """Room names must be unique."""
        Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        with self.assertRaises(IntegrityError):
            Room.objects.create(name="101A", capacity=25, room_type="LAB", school=self.school)
