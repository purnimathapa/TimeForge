import json
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from academics.models import Section, Subject, TeacherProfile, ClassSession
from accounts.models import User
from core.models import Room, Semester, Department
from scheduling.models import Constraint, TimeSlot
from timetable.models import Timetable, TimetableSlot
from timetable.views import _get_timetable


class GetTimetableResolutionTests(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26G",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
        )
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher = User.objects.create_user(
            username="teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.draft = Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.DRAFT,
        )
        self.published = Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.PUBLISHED,
        )

    def _request_for(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_non_admin_does_not_return_draft(self):
        request = self._request_for(self.teacher)
        timetable, _all = _get_timetable(request, self.semester)

        self.assertEqual(timetable, self.published)

    def test_non_admin_ignores_explicit_draft_id(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", {"timetable_id": self.draft.pk})
        request.user = self.teacher
        timetable, _all = _get_timetable(request, self.semester)

        self.assertIsNone(timetable)

    def test_admin_falls_back_to_draft_when_no_published(self):
        self.published.delete()
        request = self._request_for(self.admin)
        timetable, _all = _get_timetable(request, self.semester)

        self.assertEqual(timetable, self.draft)


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
        self.assert_admin_only('timetable:reports')

        # Full institution export remains admin-only
        self.assert_admin_only('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'})

        # Write endpoints
        self.assert_admin_only('timetable:move_slot', post=True, data={})
        self.assert_admin_only('timetable:unlock_slot', post=True, data={})


class TeacherReadAccessTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username="viewer_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.other_teacher_user = User.objects.create_user(
            username="other_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="VT001",
        )
        TeacherProfile.objects.create(
            user=self.other_teacher_user,
            employee_id="VT002",
        )

        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26R",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        self.section = Section.objects.create(
            name="10A",
            year=1,
            section_label="A",
            semester=self.semester,
            department=self.department,
        )
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
            department=self.department,
        )
        self.timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.class_session = ClassSession.objects.create(
            section=self.section,
            subject=self.subject,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.PUBLISHED,
        )
        self.slot = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.class_session,
            timeslot=self.timeslot,
            room=self.room,
            teacher=self.teacher,
        )
        self.client.login(username="viewer_teacher", password="password")

    def test_teacher_can_browse_institution_grid_views(self):
        for url_name in ('timetable:teacher_view', 'timetable:room_view', 'timetable:section_view'):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, msg=url_name)

    def test_teacher_can_select_other_teacher_grid(self):
        response = self.client.get(
            reverse('timetable:teacher_view'),
            {'teacher_id': self.other_teacher_user.teacher_profile.pk},
        )
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_move_slots(self):
        response = self.client.post(
            reverse('timetable:move_slot'),
            data=json.dumps({'slot_id': self.slot.pk}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_export_room_and_section(self):
        room_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'}),
            {'room_id': self.room.pk},
        )
        self.assertEqual(room_export.status_code, 200)
        self.assertEqual(room_export['Content-Type'], 'application/pdf')

        section_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'section', 'file_format': 'xlsx'}),
            {'section_id': self.section.pk},
        )
        self.assertEqual(section_export.status_code, 200)
        self.assertEqual(
            section_export['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_teacher_cannot_export_full_institution(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'}),
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_version_selector_lists_published_only(self):
        Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.DRAFT,
        )
        response = self.client.get(reverse('timetable:room_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['all_timetables']), [self.timetable])


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
