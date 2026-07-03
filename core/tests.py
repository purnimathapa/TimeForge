from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.test import TestCase

from core.models import Room, Semester


class SemesterModelTests(TestCase):
    def test_single_active_semester(self):
        """Activating a semester should deactivate any previously active semester."""
        sem1 = Semester.objects.create(name="Fall 2026", code="F26", start_date="2026-08-01", end_date="2026-12-15", is_active=True)
        
        with self.assertRaises(ValidationError):
            Semester.objects.create(name="Spring 2027", code="S27", start_date="2027-01-10", end_date="2027-05-20", is_active=True)

    def test_deactivating_semester(self):
        """Deactivating a semester should leave zero active semesters."""
        sem = Semester.objects.create(name="Fall 2026", code="F26", start_date="2026-08-01", end_date="2026-12-15", is_active=True)
        sem.is_active = False
        sem.save()
        self.assertFalse(Semester.objects.filter(is_active=True).exists())


class RoomModelTests(TestCase):
    def test_room_creation(self):
        """Room should be created successfully with valid data."""
        room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        self.assertEqual(room.name, "101A")
        self.assertEqual(room.capacity, 30)

    def test_room_name_unique(self):
        """Room names must be unique."""
        Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        with self.assertRaises(IntegrityError):
            Room.objects.create(name="101A", capacity=25, room_type="LAB")
