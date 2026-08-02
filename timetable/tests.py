"""
timetable/tests.py — automated and integration tests for timetable workflows.

Test layers in this module:
  Unit-ish helpers   — GetTimetableResolutionTests (_get_timetable resolution rules)
  Permission / auth  — TimetablePermissionTests, TeacherReadAccessTests,
                       ClassRepReadAccessTests (role gates on grid + export URLs)
  Workflow           — TimetablePublishWorkflowTests (publish, discard, archive)
  JSON editor        — BatchEditorTests, TimetableEditLockTests (move/validate/publish)
  End-to-end         — TimetableIntegrationTests (generate → grid → move → export)

Run all timetable tests:
  python manage.py test timetable.tests --verbosity=2

Coverage gaps (intentional TODOs for later):
  - MyRoutineView / my_routine URL (routine filtration)
  - Full admin CRUD view smoke tests (covered partly in core.tests.test_tenant_isolation)
"""

import json
from datetime import timedelta

from django.core.management import call_command
from django.db.utils import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from academics.models import Course, Subject, TeacherProfile, ClassSession
from accounts.models import User
from core.models import Room, Session, Department
from core.testing import get_test_school
from scheduling.models import TimeSlot
from timetable.models import (
    DraftChangeSet,
    Timetable,
    TimetableEditLock,
    TimetableSlot,
    acquire_lock,
)
from timetable.views import _get_timetable


class GetTimetableResolutionTests(TestCase):
    def setUp(self):
        self.school = get_test_school(code="f26g")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher = User.objects.create_user(
            username="teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        self.published = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.PUBLISHED,
        )

    def _request_for(self, user):
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        return request

    def test_non_admin_does_not_return_draft(self):
        request = self._request_for(self.teacher)
        timetable, _all = _get_timetable(request, self.session)

        self.assertEqual(timetable, self.published)

    def test_non_admin_ignores_explicit_draft_id(self):
        from django.test import RequestFactory

        request = RequestFactory().get("/", {"timetable_id": self.draft.pk})
        request.user = self.teacher
        timetable, _all = _get_timetable(request, self.session)

        self.assertIsNone(timetable)

    def test_admin_falls_back_to_draft_when_no_published(self):
        self.published.delete()
        request = self._request_for(self.admin)
        timetable, _all = _get_timetable(request, self.session)

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
        self.assert_admin_only('timetable:validate_batch', post=True, data={})
        self.assert_admin_only('timetable:publish_change_set', post=True, data={})
        self.assert_admin_only('timetable:publish_timetable', kwargs={'pk': 999}, post=True)
        self.assert_admin_only('timetable:discard_timetable', kwargs={'pk': 999}, post=True)


class TimetablePublishWorkflowTests(TestCase):
    def setUp(self):
        self.school = get_test_school(code="f26p")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.admin = User.objects.create_superuser(username="pub_admin", password="password")
        self.teacher = User.objects.create_user(
            username="pub_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        TeacherProfile.objects.create(user=self.teacher, employee_id="PT1")

        self.department = Department.objects.create(name="CS", code="CS", school=self.school)
        self.course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course_level = self.course.levels.get(level=1)
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
        )
        self.subject.departments.add(self.department)
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.teacher_profile = TeacherProfile.objects.get(user=self.teacher)
        self.class_session = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level,
            subject=self.subject,
            teacher=self.teacher_profile,
            periods_per_week=1,
        )

    def _add_slot(self, timetable):
        return TimetableSlot.objects.create(
            timetable=timetable,
            class_session=self.class_session,
            timeslot=self.timeslot,
            room=self.room,
            teacher=self.teacher_profile,
        )

    def test_publish_draft_archives_previous_published(self):
        old_published = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.PUBLISHED,
            version=1,
        )
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
            version=2,
        )
        self._add_slot(old_published)
        self._add_slot(draft)

        self.client.login(username="pub_admin", password="password")
        response = self.client.post(reverse('timetable:publish_timetable', kwargs={'pk': draft.pk}))

        self.assertEqual(response.status_code, 302)
        old_published.refresh_from_db()
        draft.refresh_from_db()

        self.assertEqual(old_published.status, Timetable.Status.ARCHIVED)
        self.assertEqual(draft.status, Timetable.Status.PUBLISHED)
        self.assertIsNotNone(draft.published_at)
        self.assertEqual(draft.published_by, self.admin)

    def test_teacher_grid_uses_published_not_draft(self):
        published = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.PUBLISHED,
            version=1,
        )
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
            version=2,
        )
        self._add_slot(published)

        self.client.login(username="pub_teacher", password="password")
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "MATH101")

        self.client.login(username="pub_admin", password="password")
        self.client.post(reverse('timetable:publish_timetable', kwargs={'pk': draft.pk}))

        self.client.login(username="pub_teacher", password="password")
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "MATH101")

        published.refresh_from_db()
        self.assertEqual(published.status, Timetable.Status.ARCHIVED)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Timetable.Status.PUBLISHED)

    def test_teacher_cannot_see_draft_only_timetable(self):
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        self._add_slot(draft)

        self.client.login(username="pub_teacher", password="password")
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "MATH101")

    def test_non_admin_cannot_publish(self):
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )

        self.client.login(username="pub_teacher", password="password")
        response = self.client.post(reverse('timetable:publish_timetable', kwargs={'pk': draft.pk}))
        self.assertEqual(response.status_code, 403)

        draft.refresh_from_db()
        self.assertEqual(draft.status, Timetable.Status.DRAFT)

    def test_discard_draft_archives_timetable(self):
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        slot = self._add_slot(draft)

        self.client.login(username="pub_admin", password="password")
        response = self.client.post(reverse('timetable:discard_timetable', kwargs={'pk': draft.pk}))

        self.assertEqual(response.status_code, 302)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Timetable.Status.ARCHIVED)
        self.assertTrue(TimetableSlot.objects.filter(pk=slot.pk).exists())


class TeacherReadAccessTests(TestCase):
    """Integration tests for teacher grid/export access and routine filtration params.

    Asserts teachers can browse grids with ?teacher_id= and that published-only
    timetable rules apply on read paths (no draft leakage).
    """
    def setUp(self):
        self.school = get_test_school(code="f26r")
        self.teacher_user = User.objects.create_user(
            username="viewer_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.other_teacher_user = User.objects.create_user(
            username="other_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="VT001",
        )
        TeacherProfile.objects.create(
            user=self.other_teacher_user,
            employee_id="VT002",
        )

        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course_level = self.course.levels.get(level=1)
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
        )
        self.subject.departments.add(self.department)
        self.timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.class_session = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level,
            subject=self.subject,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            session=self.session,
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
        for url_name in ('timetable:teacher_view', 'timetable:room_view', 'timetable:course_level_view'):
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

    def test_teacher_can_export_room_and_course_level(self):
        room_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'}),
            {'room_id': self.room.pk},
        )
        self.assertEqual(room_export.status_code, 200)
        self.assertEqual(room_export['Content-Type'], 'application/pdf')

        course_level_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'course_level', 'file_format': 'xlsx'}),
            {'course_level_id': self.course_level.pk},
        )
        self.assertEqual(course_level_export.status_code, 200)
        self.assertEqual(
            course_level_export['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    def test_teacher_cannot_export_full_institution(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'}),
        )
        self.assertEqual(response.status_code, 403)

    def test_teacher_export_ignores_other_teacher_id(self):
        """A teacher cannot pull another teacher's schedule via ?teacher_id=."""
        import zipfile
        from io import BytesIO

        from django.test import RequestFactory

        from timetable.views import ExportTimetableView

        other = self.other_teacher_user.teacher_profile
        other_subject = Subject.objects.create(
            name="Physics",
            code="PHYS999",
            lecture_hours_per_week=1,
        )
        other_subject.departments.add(self.department)
        other_session = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level,
            subject=other_subject,
            teacher=other,
            periods_per_week=1,
        )
        other_timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=2,
            start_time="10:00",
            end_time="11:00",
            is_active=True,
        )
        other_room = Room.objects.create(
            name="202B", capacity=30, room_type="LECTURE", school=self.school,
        )
        TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=other_session,
            timeslot=other_timeslot,
            room=other_room,
            teacher=other,
        )

        factory = RequestFactory()
        request = factory.get(
            reverse('timetable:export', kwargs={'scope': 'teacher', 'file_format': 'xlsx'}),
            {'teacher_id': other.pk},
        )
        request.user = self.teacher_user
        view = ExportTimetableView()
        selected = view._selected_teacher(request)
        self.assertEqual(selected.pk, self.teacher.pk)
        slots, _title, label = view._resolve_slots(request, self.timetable, 'teacher')
        self.assertTrue(slots)
        self.assertTrue(all(slot.teacher_id == self.teacher.pk for slot in slots))
        self.assertFalse(any(slot.teacher_id == other.pk for slot in slots))
        self.assertIn(str(self.teacher), label)
        self.assertNotIn(str(other), label)

        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'teacher', 'file_format': 'xlsx'}),
            {'teacher_id': other.pk},
        )
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(BytesIO(response.content)) as archive:
            sheet_xml = archive.read('xl/worksheets/sheet1.xml')
        self.assertIn(b'MATH101', sheet_xml)
        self.assertNotIn(b'PHYS999', sheet_xml)

    def test_teacher_version_selector_lists_published_only(self):
        Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        response = self.client.get(reverse('timetable:room_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['all_timetables']), [self.timetable])

    def test_teacher_and_room_can_select_timetable_version(self):
        """Teacher and Room grids honour ?timetable_id= the same as Course Level."""
        draft = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        admin = User.objects.create_superuser(username="ver_admin", password="password")
        self.client.login(username="ver_admin", password="password")

        for url_name in (
            'timetable:teacher_view',
            'timetable:room_view',
            'timetable:course_level_view',
        ):
            response = self.client.get(reverse(url_name), {'timetable_id': draft.pk})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['timetable'].pk, draft.pk)
            self.assertIn(draft, list(response.context['all_timetables']))
            self.assertIn(self.timetable, list(response.context['all_timetables']))
            self.assertContains(response, 'Timetable version')
            self.assertContains(response, f'v{draft.version}')


class ClassRepReadAccessTests(TestCase):
    def setUp(self):
        from academics.models import ClassRepProfile

        self.school = get_test_school(code="f26cr2")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course_level = self.course.levels.get(level=1)
        self.other_course = Course.objects.create(
            name="Bachelor of Information Technology",
            code="BIT",
            department=self.department,
        )
        self.other_course_level = self.other_course.levels.get(level=1)
        self.cr_user = User.objects.create_user(
            username="classrep",
            password="password",
            role=User.RoleChoices.CLASS_REP,
            school=self.school,
        )
        self.class_rep_profile = ClassRepProfile.objects.create(
            user=self.cr_user,
            course_level=self.course_level,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher1",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="CR-T1",
        )
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.subject = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
        )
        self.subject.departments.add(self.department)
        self.timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.class_session = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level,
            subject=self.subject,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.PUBLISHED,
        )
        self.slot = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.class_session,
            timeslot=self.timeslot,
            room=self.room,
            teacher=self.teacher,
        )
        self.client.login(username="classrep", password="password")

    def test_class_rep_can_browse_read_only_grids(self):
        for url_name in ('timetable:teacher_view', 'timetable:room_view', 'timetable:course_level_view'):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, msg=url_name)

    def test_class_rep_course_level_view_defaults_to_assigned_course_level(self):
        response = self.client.get(reverse('timetable:course_level_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_course_level'], self.course_level)

    def test_class_rep_cannot_move_slots(self):
        response = self.client.post(
            reverse('timetable:move_slot'),
            data=json.dumps({'slot_id': self.slot.pk}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_class_rep_can_export_room_and_course_level(self):
        room_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'}),
            {'room_id': self.room.pk},
        )
        self.assertEqual(room_export.status_code, 200)

        course_level_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'course_level', 'file_format': 'xlsx'}),
        )
        self.assertEqual(course_level_export.status_code, 200)

    def test_class_rep_cannot_export_full_institution(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'}),
        )
        self.assertEqual(response.status_code, 403)


class BatchEditorTests(TestCase):
    """Integration tests for the JSON batch editor (move, validate, publish change sets).

    Uses self.client.post with application/json payloads against timetable editor
    endpoints; verifies optimistic UI workflow without a browser.
    """
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.teacher_user = User.objects.create_user(
            username="batch_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="BT001",
        )
        self.school = get_test_school(code="f26b")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.room1 = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.room2 = Room.objects.create(name="102A", capacity=30, room_type="LECTURE", school=self.school)
        self.course1 = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course2 = Course.objects.create(
            name="Bachelor of Information Technology",
            code="BIT",
            department=self.department,
        )
        self.course_level1 = self.course1.levels.get(level=1)
        self.course_level2 = self.course2.levels.get(level=1)
        self.subject1 = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
        )
        self.subject1.departments.add(self.department)
        self.subject2 = Subject.objects.create(
            name="Physics",
            code="PHY101",
            lecture_hours_per_week=1,
        )
        self.subject2.departments.add(self.department)
        self.timeslot1 = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.timeslot2 = TimeSlot.objects.create(
            day_of_week=1,
            period_number=2,
            start_time="10:00",
            end_time="11:00",
            is_active=True,
        )
        self.timeslot3 = TimeSlot.objects.create(
            day_of_week=2,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.session1 = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level1,
            subject=self.subject1,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.session2 = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level2,
            subject=self.subject2,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        self.slot1 = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.session1,
            timeslot=self.timeslot1,
            room=self.room1,
            teacher=self.teacher,
        )
        self.slot2 = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.session2,
            timeslot=self.timeslot2,
            room=self.room2,
            teacher=self.teacher,
        )
        self.client.login(username="admin", password="password")

    def _validate(self, moves):
        return self.client.post(
            reverse('timetable:validate_batch'),
            data=json.dumps({'timetable_id': self.timetable.pk, 'moves': moves}),
            content_type='application/json',
        )

    def test_validate_empty_moves_is_valid(self):
        response = self._validate([])
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertTrue(data['is_valid'])
        self.assertEqual(data['violations'], [])
        self.assertGreaterEqual(data['soft_conflict_count'], 0)
        self.assertTrue(DraftChangeSet.objects.filter(pk=data['change_set_id'], is_valid=True).exists())

    def test_batch_detects_combined_teacher_conflict(self):
        moves = [
            {
                'slot_id': self.slot1.pk,
                'target_day': self.timeslot2.day_of_week,
                'target_period': self.timeslot2.period_number,
                'target_room': self.room1.pk,
            },
            {
                'slot_id': self.slot2.pk,
                'target_day': self.timeslot2.day_of_week,
                'target_period': self.timeslot2.period_number,
                'target_room': self.room2.pk,
            },
        ]
        response = self._validate(moves)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertFalse(data['is_valid'])
        self.assertTrue(data['violations'])

    def test_publish_after_valid_check_updates_slots(self):
        response = self._validate([
            {
                'slot_id': self.slot1.pk,
                'target_day': self.timeslot3.day_of_week,
                'target_period': self.timeslot3.period_number,
                'target_room': self.room1.pk,
            },
        ])
        change_set_id = response.json()['change_set_id']
        self.assertTrue(response.json()['is_valid'])

        publish_response = self.client.post(
            reverse('timetable:publish_change_set'),
            data=json.dumps({'change_set_id': change_set_id}),
            content_type='application/json',
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertTrue(publish_response.json()['ok'])

        self.slot1.refresh_from_db()
        self.assertEqual(self.slot1.timeslot_id, self.timeslot3.pk)
        self.assertEqual(self.slot1.room_id, self.room1.pk)
        self.assertTrue(self.slot1.is_locked)
        self.assertTrue(self.slot1.is_manual)

        change_set = DraftChangeSet.objects.get(pk=change_set_id)
        self.assertTrue(change_set.is_published)
        self.assertEqual(change_set.moves.count(), 0)

    def test_discard_does_not_change_slots(self):
        original_timeslot_id = self.slot1.timeslot_id
        response = self._validate([
            {
                'slot_id': self.slot1.pk,
                'target_day': self.timeslot2.day_of_week,
                'target_period': self.timeslot2.period_number,
                'target_room': self.room1.pk,
            },
        ])
        change_set_id = response.json()['change_set_id']

        discard_response = self.client.post(
            reverse('timetable:discard_change_set'),
            data=json.dumps({'change_set_id': change_set_id}),
            content_type='application/json',
        )
        self.assertEqual(discard_response.status_code, 200)

        self.slot1.refresh_from_db()
        self.assertEqual(self.slot1.timeslot_id, original_timeslot_id)

        change_set = DraftChangeSet.objects.get(pk=change_set_id)
        self.assertTrue(change_set.is_discarded)
        self.assertEqual(change_set.moves.count(), 0)

    def test_publish_without_valid_check_returns_400(self):
        change_set = DraftChangeSet.objects.create(
            timetable=self.timetable,
            created_by=self.admin,
            is_valid=False,
        )
        response = self.client.post(
            reverse('timetable:publish_change_set'),
            data=json.dumps({'change_set_id': change_set.pk}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()['ok'])

    def test_teacher_cannot_validate_or_publish(self):
        self.client.login(username="batch_teacher", password="password")
        validate_response = self._validate([])
        self.assertEqual(validate_response.status_code, 403)

        change_set = DraftChangeSet.objects.create(
            timetable=self.timetable,
            created_by=self.admin,
            is_valid=True,
        )
        publish_response = self.client.post(
            reverse('timetable:publish_change_set'),
            data=json.dumps({'change_set_id': change_set.pk}),
            content_type='application/json',
        )
        self.assertEqual(publish_response.status_code, 403)


class TimetableIntegrationTests(TestCase):
    """Full HTTP integration: management command → views → JSON editor → export.

    Exercises the generate_timetable command, grid rendering, slot move API,
    and PDF/XLSX export in one chained flow. Uses Django TestCase + self.client
    (real URL routing, middleware, and view code paths).
    """
    def setUp(self):
        self.admin = User.objects.create_superuser(username="admin", password="password")
        self.client.login(username="admin", password="password")

        self.school = get_test_school(code="f26t")
        # 1. Seed minimal required data
        self.session = Session.objects.create(
            name="Fall 2026 Test",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS", school=self.school)
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.subject = Subject.objects.create(
            name="Math", code="MATH101", lecture_hours_per_week=1,
        )
        self.subject.departments.add(self.department)
        self.course = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course_level = self.course.levels.get(level=1)

        self.teacher_user = User.objects.create_user(username="teacher1", password="password", role=User.RoleChoices.TEACHER)
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user, employee_id="T1")

        self.timeslot = TimeSlot.objects.create(day_of_week=1, period_number=1, start_time="09:00", end_time="10:00", is_active=True)
        self.timeslot_2 = TimeSlot.objects.create(day_of_week=1, period_number=2, start_time="10:00", end_time="11:00", is_active=True)

        self.class_session = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level,
            subject=self.subject,
            teacher=self.teacher,
            periods_per_week=1
        )

    def test_full_flow(self):
        # 2. Simulate generation flow
        call_command('generate_timetable', '--session', self.session.name)

        timetable = Timetable.objects.get(session=self.session)
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


class TimetableEditLockTests(TestCase):
    def setUp(self):
        self.school = get_test_school(code="f26l")
        self.session = Session.objects.create(
            name="Fall 2026",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
            school=self.school,
        )
        self.admin_a = User.objects.create_superuser(
            username="lock_admin_a",
            password="password",
            first_name="Alice",
            last_name="Admin",
        )
        self.admin_b = User.objects.create_superuser(
            username="lock_admin_b",
            password="password",
            first_name="Bob",
            last_name="Admin",
        )
        self.teacher_user = User.objects.create_user(
            username="lock_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="LK001",
        )
        self.other_teacher_user = User.objects.create_user(
            username="lock_teacher_b",
            password="password",
            role=User.RoleChoices.TEACHER,
            school=self.school,
        )
        self.other_teacher = TeacherProfile.objects.create(
            user=self.other_teacher_user,
            employee_id="LK002",
        )
        self.department = Department.objects.create(name="CS", code="CS", school=self.school)
        self.room1 = Room.objects.create(name="101A", capacity=30, room_type="LECTURE", school=self.school)
        self.room2 = Room.objects.create(name="102A", capacity=30, room_type="LECTURE", school=self.school)
        self.course1 = Course.objects.create(
            name="BE Computer Engineering",
            code="BE-CE",
            department=self.department,
        )
        self.course2 = Course.objects.create(
            name="Bachelor of Information Technology",
            code="BIT",
            department=self.department,
        )
        self.course_level1 = self.course1.levels.get(level=1)
        self.course_level2 = self.course2.levels.get(level=1)
        self.subject1 = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
        )
        self.subject1.departments.add(self.department)
        self.subject2 = Subject.objects.create(
            name="Physics",
            code="PHY101",
            lecture_hours_per_week=1,
        )
        self.subject2.departments.add(self.department)
        self.timeslot1 = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.timeslot2 = TimeSlot.objects.create(
            day_of_week=1,
            period_number=2,
            start_time="10:00",
            end_time="11:00",
            is_active=True,
        )
        self.session1 = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level1,
            subject=self.subject1,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.session2 = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level2,
            subject=self.subject2,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            session=self.session,
            status=Timetable.Status.DRAFT,
        )
        self.slot1 = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.session1,
            timeslot=self.timeslot1,
            room=self.room1,
            teacher=self.teacher,
        )
        self.slot2 = TimetableSlot.objects.create(
            timetable=self.timetable,
            class_session=self.session2,
            timeslot=self.timeslot2,
            room=self.room2,
            teacher=self.teacher,
        )

    def _validate_as(self, username, moves=None):
        self.client.login(username=username, password="password")
        return self.client.post(
            reverse('timetable:validate_batch'),
            data=json.dumps({'timetable_id': self.timetable.pk, 'moves': moves or []}),
            content_type='application/json',
        )

    def test_user_b_blocked_while_user_a_holds_lock(self):
        response_a = self._validate_as("lock_admin_a")
        self.assertEqual(response_a.status_code, 200)

        response_b = self._validate_as("lock_admin_b")
        self.assertEqual(response_b.status_code, 409)
        data = response_b.json()
        self.assertFalse(data['ok'])
        self.assertIn('Alice Admin', data['locked_by'])

    def test_user_b_can_acquire_after_lock_timeout(self):
        self._validate_as("lock_admin_a")
        lock = TimetableEditLock.objects.get(timetable=self.timetable)
        TimetableEditLock.objects.filter(pk=lock.pk).update(
            locked_at=timezone.now() - timedelta(minutes=TimetableEditLock.LOCK_TIMEOUT_MINUTES + 1),
        )

        response_b = self._validate_as("lock_admin_b")
        self.assertEqual(response_b.status_code, 200)
        lock.refresh_from_db()
        self.assertEqual(lock.locked_by, self.admin_b)

    def test_publish_releases_lock(self):
        self.client.login(username="lock_admin_a", password="password")
        validate_response = self._validate_as("lock_admin_a")
        change_set_id = validate_response.json()['change_set_id']

        publish_response = self.client.post(
            reverse('timetable:publish_change_set'),
            data=json.dumps({'change_set_id': change_set_id}),
            content_type='application/json',
        )
        self.assertEqual(publish_response.status_code, 200)
        self.assertFalse(TimetableEditLock.objects.filter(timetable=self.timetable).exists())

        response_b = self._validate_as("lock_admin_b")
        self.assertEqual(response_b.status_code, 200)

    def test_discard_releases_lock(self):
        self.client.login(username="lock_admin_a", password="password")
        validate_response = self._validate_as("lock_admin_a")
        change_set_id = validate_response.json()['change_set_id']

        discard_response = self.client.post(
            reverse('timetable:discard_change_set'),
            data=json.dumps({'change_set_id': change_set_id}),
            content_type='application/json',
        )
        self.assertEqual(discard_response.status_code, 200)
        self.assertFalse(TimetableEditLock.objects.filter(timetable=self.timetable).exists())

    def test_teacher_double_booking_rejected_at_db_level(self):
        session3 = ClassSession.objects.create(
            session=self.session,
            course_level=self.course_level2,
            subject=self.subject2,
            teacher=self.teacher,
            periods_per_week=1,
        )
        with self.assertRaises(IntegrityError):
            TimetableSlot.objects.create(
                timetable=self.timetable,
                class_session=session3,
                timeslot=self.timeslot1,
                room=self.room2,
                teacher=self.teacher,
            )

    def test_grid_shows_lock_banner_for_other_admin(self):
        acquire_lock(self.timetable, self.admin_a)
        self.client.login(username="lock_admin_b", password="password")
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['edit_lock_held_by_other'])
        self.assertContains(response, "Alice Admin")
