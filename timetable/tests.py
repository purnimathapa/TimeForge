import json
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from academics.models import Section, Subject, TeacherProfile, ClassSession
from accounts.models import User
from core.models import Room, Semester, Department
from scheduling.models import Constraint, TimeSlot
from timetable.models import Timetable, TimetableSlot


class TimetablePermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher = User.objects.create_user(username="teacher", password="password", role=User.RoleChoices.TEACHER)

    def assert_admin_only(self, url_name, kwargs=None, post=False, data=None):
        self.client.logout()
        url = reverse(url_name, kwargs=kwargs)
        
        # Unauthenticated
        method = self.client.post if post else self.client.get
        response = method(url, data=data, content_type='application/json')
        if response.status_code == 302:
            self.assertIn('/accounts/login/', response.url)
        else:
            self.assertEqual(response.status_code, 403)

        # Teacher
        self.client.login(username="teacher", password="password")
        response = method(url, data=data, content_type='application/json')
        self.assertEqual(response.status_code, 403)

        # Admin
        self.client.login(username="admin", password="password")
        response = method(url, data=data, content_type='application/json')
        # We just care it's not 403 or redirect to login (could be 200, 400, 404, etc.)
        self.assertNotIn(response.status_code, [403])

    def test_admin_only_views(self):
        self.assert_admin_only('timetable:generate')
        self.assert_admin_only('timetable:list')
        self.assert_admin_only('timetable:detail', kwargs={'pk': 999})
        self.assert_admin_only('timetable:room_view')
        self.assert_admin_only('timetable:section_view')
        self.assert_admin_only('timetable:reports')
        
        # Exports
        self.assert_admin_only('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'})
        self.assert_admin_only('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'})
        self.assert_admin_only('timetable:export', kwargs={'scope': 'section', 'file_format': 'xlsx'})

        # Endpoints
        self.assert_admin_only('timetable:move_slot', post=True, data={})
        self.assert_admin_only('timetable:unlock_slot', post=True, data={})


class TimetableIntegrationTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.client.login(username="admin", password="password")

        # 1. Seed minimal required data
        self.semester = Semester.objects.create(name="Fall 2026 Test", code="F26T", start_date="2026-08-01", end_date="2026-12-15", is_active=True)
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        self.subject = Subject.objects.create(name="Math", code="MATH101", lecture_hours_per_week=1, department=self.department)
        self.section = Section.objects.create(name="10A", year=1, section_label="A", semester=self.semester, department=self.department)
        
        self.teacher_user = User.objects.create_user(username="teacher1", password="password", role=User.RoleChoices.TEACHER)
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, employee_id="T1")

        self.timeslot = TimeSlot.objects.create(day_of_week=1, period_number=1, start_time="09:00", end_time="10:00", is_active=True)
        self.timeslot_2 = TimeSlot.objects.create(day_of_week=1, period_number=2, start_time="10:00", end_time="11:00", is_active=True)

        self.class_session = ClassSession.objects.create(
            section=self.section,
            subject=self.subject,
            teacher=self.teacher,
            periods_per_week=1
        )

    def test_full_flow(self):
        # 2. Simulate generation flow
        call_command('generate_timetable', '--semester', self.semester.code)

        timetable = Timetable.objects.get(semester=self.semester)
        self.assertEqual(timetable.status, Timetable.Status.DRAFT)
        
        slot = TimetableSlot.objects.filter(timetable=timetable).first()
        self.assertIsNotNone(slot)

        # 3. Assert queryable via grid views
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MATH101")

        # 4. Drag-and-drop validation
        # Valid move to period 2
        move_url = reverse('timetable:move_slot')
        valid_payload = {
            'slot_id': slot.pk,
            'target_day': self.timeslot_2.day_of_week,
            'target_period': self.timeslot_2.period_number,
            'target_room': self.room.pk
        }
        res = self.client.post(move_url, data=json.dumps(valid_payload), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()['ok'])

        # 5. Export views
        export_url = reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'})
        res_pdf = self.client.get(export_url)
        self.assertEqual(res_pdf.status_code, 200)
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

        export_xlsx_url = reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'xlsx'})
        res_xlsx = self.client.get(export_xlsx_url)
        self.assertEqual(res_xlsx.status_code, 200)
        self.assertEqual(res_xlsx['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
