import json
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from academics.models import Section, Subject, TeacherProfile, ClassSession
from accounts.models import User
from core.models import Room, Semester, Department
from scheduling.models import Constraint, TimeSlot
from timetable.models import DraftChangeSet, Timetable, TimetableSlot
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
        self.assert_admin_only('timetable:validate_batch', post=True, data={})
        self.assert_admin_only('timetable:publish_change_set', post=True, data={})
        self.assert_admin_only('timetable:publish_timetable', kwargs={'pk': 999}, post=True)
        self.assert_admin_only('timetable:discard_timetable', kwargs={'pk': 999}, post=True)


class TimetablePublishWorkflowTests(TestCase):
    def setUp(self):
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26P",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
        )
        self.admin = User.objects.create_superuser(username="pub_admin", password="password")
        self.teacher = User.objects.create_user(
            username="pub_teacher",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher, employee_id="PT1")

        self.department = Department.objects.create(name="CS", code="CS")
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
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        self.timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time="09:00",
            end_time="10:00",
            is_active=True,
        )
        self.teacher_profile = TeacherProfile.objects.get(user=self.teacher)
        self.class_session = ClassSession.objects.create(
            section=self.section,
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
            semester=self.semester,
            status=Timetable.Status.PUBLISHED,
            version=1,
        )
        draft = Timetable.objects.create(
            semester=self.semester,
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
            semester=self.semester,
            status=Timetable.Status.PUBLISHED,
            version=1,
        )
        draft = Timetable.objects.create(
            semester=self.semester,
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
            semester=self.semester,
            status=Timetable.Status.DRAFT,
        )
        self._add_slot(draft)

        self.client.login(username="pub_teacher", password="password")
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "MATH101")

    def test_non_admin_cannot_publish(self):
        draft = Timetable.objects.create(
            semester=self.semester,
            status=Timetable.Status.DRAFT,
        )

        self.client.login(username="pub_teacher", password="password")
        response = self.client.post(reverse('timetable:publish_timetable', kwargs={'pk': draft.pk}))
        self.assertEqual(response.status_code, 403)

        draft.refresh_from_db()
        self.assertEqual(draft.status, Timetable.Status.DRAFT)

    def test_discard_draft_archives_timetable(self):
        draft = Timetable.objects.create(
            semester=self.semester,
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


class ClassRepReadAccessTests(TestCase):
    def setUp(self):
        from academics.models import ClassRepProfile

        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26CR2",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.section = Section.objects.create(
            name="10A",
            year=1,
            section_label="A",
            semester=self.semester,
            department=self.department,
        )
        self.other_section = Section.objects.create(
            name="10B",
            year=1,
            section_label="B",
            semester=self.semester,
            department=self.department,
        )
        self.cr_user = User.objects.create_user(
            username="classrep",
            password="password",
            role=User.RoleChoices.CLASS_REP,
        )
        self.class_rep_profile = ClassRepProfile.objects.create(
            user=self.cr_user,
            section=self.section,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher1",
            password="password",
            role=User.RoleChoices.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            employee_id="CR-T1",
        )
        self.room = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
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
        self.client.login(username="classrep", password="password")

    def test_class_rep_can_browse_read_only_grids(self):
        for url_name in ('timetable:teacher_view', 'timetable:room_view', 'timetable:section_view'):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, msg=url_name)

    def test_class_rep_section_view_defaults_to_assigned_section(self):
        response = self.client.get(reverse('timetable:section_view'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['selected_section'], self.section)

    def test_class_rep_cannot_move_slots(self):
        response = self.client.post(
            reverse('timetable:move_slot'),
            data=json.dumps({'slot_id': self.slot.pk}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)

    def test_class_rep_can_export_room_and_section(self):
        room_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'}),
            {'room_id': self.room.pk},
        )
        self.assertEqual(room_export.status_code, 200)

        section_export = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'section', 'file_format': 'xlsx'}),
        )
        self.assertEqual(section_export.status_code, 200)

    def test_class_rep_cannot_export_full_institution(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'full', 'file_format': 'pdf'}),
        )
        self.assertEqual(response.status_code, 403)


class BatchEditorTests(TestCase):
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
        self.semester = Semester.objects.create(
            name="Fall 2026",
            code="F26B",
            start_date="2026-08-01",
            end_date="2026-12-15",
            is_active=True,
        )
        self.department = Department.objects.create(name="Computer Science", code="CS")
        self.room1 = Room.objects.create(name="101A", capacity=30, room_type="LECTURE")
        self.room2 = Room.objects.create(name="102A", capacity=30, room_type="LECTURE")
        self.section1 = Section.objects.create(
            name="10A",
            year=1,
            section_label="A",
            semester=self.semester,
            department=self.department,
        )
        self.section2 = Section.objects.create(
            name="10B",
            year=1,
            section_label="B",
            semester=self.semester,
            department=self.department,
        )
        self.subject1 = Subject.objects.create(
            name="Math",
            code="MATH101",
            lecture_hours_per_week=1,
            department=self.department,
        )
        self.subject2 = Subject.objects.create(
            name="Physics",
            code="PHY101",
            lecture_hours_per_week=1,
            department=self.department,
        )
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
            section=self.section1,
            subject=self.subject1,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.session2 = ClassSession.objects.create(
            section=self.section2,
            subject=self.subject2,
            teacher=self.teacher,
            periods_per_week=1,
        )
        self.timetable = Timetable.objects.create(
            semester=self.semester,
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
        self.assertGreaterEqual(data['penalty_score'], 0)
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
