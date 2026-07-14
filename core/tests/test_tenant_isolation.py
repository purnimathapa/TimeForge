"""
Cross-tenant isolation tests (release-blockers).

These tests are release-blockers for any multi-school deployment. They verify
that School A staff never see School B data via lists, detail views, grids,
exports, or JSON editor endpoints.

Fixture note: School A has the active semester; School B's semester is inactive
so generate-timetable always targets School A for the School A admin.

When CI is configured, run this module first:
    python manage.py test core.tests.test_tenant_isolation
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from academics.models import ClassSession, Section, Subject, TeacherProfile
from core.models import Department, Room, School, Semester
from scheduling.models import TimeSlot
from timetable.models import Timetable, TimetableSlot


@dataclass
class TenantDataset:
    """Minimal parallel dataset for one school."""

    label: str
    school: School
    admin: User
    teacher_user: User
    teacher: TeacherProfile
    department: Department
    room: Room
    semester: Semester
    section: Section
    subject: Subject
    class_session: ClassSession
    timeslot: TimeSlot
    timetable: Timetable
    slot: TimetableSlot

    @property
    def subject_code(self) -> str:
        return self.subject.code


def build_tenant_dataset(
    *,
    label: str,
    school_code: str,
    school_name: str,
    semester_active: bool,
    timeslot: TimeSlot,
) -> TenantDataset:
    """Create a minimal isolated dataset for one school."""
    school = School.objects.create(name=school_name, code=school_code, is_active=True)

    admin = User.objects.create_user(
        username=f'admin_{label.lower()}',
        password='password',
        role=User.RoleChoices.ADMIN,
        school=school,
    )
    teacher_user = User.objects.create_user(
        username=f'teacher_{label.lower()}',
        password='password',
        role=User.RoleChoices.TEACHER,
        school=school,
    )
    teacher = TeacherProfile.objects.create(
        user=teacher_user,
        employee_id=f'EMP-{label}',
    )

    department = Department.objects.create(
        name=f'{label} Department',
        code=f'DEPT-{label}',
        school=school,
    )
    room = Room.objects.create(
        name=f'{label} Room 101',
        code=f'RM-{label}',
        capacity=40,
        room_type='LECTURE',
        school=school,
    )
    semester = Semester.objects.create(
        name=f'{label} Fall 2026',
        code=f'SEM-{label}',
        start_date='2026-08-01',
        end_date='2026-12-15',
        is_active=semester_active,
        school=school,
    )
    section = Section.objects.create(
        name=f'{label} Section 10A',
        year=1,
        section_label='A',
        semester=semester,
        department=department,
    )
    subject = Subject.objects.create(
        name=f'{label} Mathematics',
        code=f'MATH-{label}',
        lecture_hours_per_week=1,
        department=department,
    )
    class_session = ClassSession.objects.create(
        section=section,
        subject=subject,
        teacher=teacher,
        periods_per_week=1,
    )
    timetable = Timetable.objects.create(
        semester=semester,
        status=Timetable.Status.PUBLISHED,
    )
    slot = TimetableSlot.objects.create(
        timetable=timetable,
        class_session=class_session,
        timeslot=timeslot,
        room=room,
        teacher=teacher,
    )

    return TenantDataset(
        label=label,
        school=school,
        admin=admin,
        teacher_user=teacher_user,
        teacher=teacher,
        department=department,
        room=room,
        semester=semester,
        section=section,
        subject=subject,
        class_session=class_session,
        timeslot=timeslot,
        timetable=timetable,
        slot=slot,
    )


class TenantIsolationTestCase(TestCase):
    """Shared two-school fixture: School A (active semester) and School B (inactive)."""

    @classmethod
    def setUpTestData(cls):
        # TimeSlot is institution-wide (shared calendar grid per MULTI_TENANCY.md).
        cls.shared_timeslot = TimeSlot.objects.create(
            day_of_week=1,
            period_number=1,
            start_time='09:00',
            end_time='10:00',
            is_active=True,
        )
        cls.school_a = build_tenant_dataset(
            label='A',
            school_code='school-a',
            school_name='School A',
            semester_active=True,
            timeslot=cls.shared_timeslot,
        )
        cls.school_b = build_tenant_dataset(
            label='B',
            school_code='school-b',
            school_name='School B',
            semester_active=False,
            timeslot=cls.shared_timeslot,
        )

    def setUp(self):
        self.client.login(username=self.school_a.admin.username, password='password')

    def _assert_list_excludes_other_tenant(self, url_name, other: TenantDataset, own: TenantDataset):
        response = self.client.get(reverse(url_name))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(own.subject_code, content)
        self.assertNotIn(other.subject_code, content)
        self.assertNotIn(other.department.code, content)


class TenantListIsolationTests(TenantIsolationTestCase):
    def test_department_list_excludes_other_school(self):
        response = self.client.get(reverse('core:department_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.school_a.department.code, content)
        self.assertNotIn(self.school_b.department.code, content)

    def test_room_list_excludes_other_school(self):
        response = self.client.get(reverse('core:room_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.school_a.room.name, content)
        self.assertNotIn(self.school_b.room.name, content)

    def test_teacher_list_excludes_other_school(self):
        response = self.client.get(reverse('academics:teacher_list'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(self.school_a.teacher.employee_id, content)
        self.assertNotIn(self.school_b.teacher.employee_id, content)

    def test_timetable_list_excludes_other_school(self):
        response = self.client.get(reverse('timetable:list'))
        self.assertEqual(response.status_code, 200)
        timetables = list(response.context['timetables'])
        timetable_ids = {t.pk for t in timetables}
        self.assertIn(self.school_a.timetable.pk, timetable_ids)
        self.assertNotIn(self.school_b.timetable.pk, timetable_ids)


class TenantDetailIsolationTests(TenantIsolationTestCase):
    def test_timetable_detail_other_school_pk_returns_404(self):
        response = self.client.get(
            reverse('timetable:detail', kwargs={'pk': self.school_b.timetable.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_publish_other_school_timetable_returns_404(self):
        response = self.client.post(
            reverse('timetable:publish_timetable', kwargs={'pk': self.school_b.timetable.pk}),
        )
        self.assertEqual(response.status_code, 404)
        self.school_b.timetable.refresh_from_db()
        self.assertEqual(self.school_b.timetable.status, Timetable.Status.PUBLISHED)


class TenantGridIsolationTests(TenantIsolationTestCase):
    def test_teacher_grid_with_other_school_teacher_id_hides_their_slots(self):
        response = self.client.get(
            reverse('timetable:teacher_view'),
            {'teacher_id': self.school_b.teacher.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.school_b.subject_code)

    def test_room_grid_with_other_school_room_id_hides_their_slots(self):
        response = self.client.get(
            reverse('timetable:room_view'),
            {'room_id': self.school_b.room.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.school_b.subject_code)

    def test_section_grid_with_other_school_section_id_hides_their_slots(self):
        response = self.client.get(
            reverse('timetable:section_view'),
            {'section_id': self.school_b.section.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.school_b.subject_code)


class TenantExportIsolationTests(TenantIsolationTestCase):
    def test_room_export_with_other_school_room_id_is_empty(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'room', 'file_format': 'pdf'}),
            {'room_id': self.school_b.room.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.content), 5000)

    def test_section_export_with_other_school_section_id_is_empty(self):
        response = self.client.get(
            reverse('timetable:export', kwargs={'scope': 'section', 'file_format': 'xlsx'}),
            {'section_id': self.school_b.section.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertLess(len(response.content), 8000)


class TenantEditorIsolationTests(TenantIsolationTestCase):
    def test_validate_batch_with_other_school_timetable_id_returns_404(self):
        response = self.client.post(
            reverse('timetable:validate_batch'),
            data=json.dumps({
                'timetable_id': self.school_b.timetable.pk,
                'moves': [],
            }),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)

    def test_discard_other_school_draft_returns_404(self):
        draft = Timetable.objects.create(
            semester=self.school_b.semester,
            status=Timetable.Status.DRAFT,
        )
        response = self.client.post(
            reverse('timetable:discard_timetable', kwargs={'pk': draft.pk}),
        )
        self.assertEqual(response.status_code, 404)


class TenantGenerateIsolationTests(TenantIsolationTestCase):
    def test_generate_does_not_create_timetable_for_other_school(self):
        b_count_before = Timetable.objects.filter(semester=self.school_b.semester).count()
        a_count_before = Timetable.objects.filter(semester=self.school_a.semester).count()

        response = self.client.post(reverse('timetable:generate'))
        self.assertEqual(response.status_code, 302)

        b_count_after = Timetable.objects.filter(semester=self.school_b.semester).count()
        self.assertEqual(b_count_before, b_count_after)
        self.assertGreaterEqual(
            Timetable.objects.filter(semester=self.school_a.semester).count(),
            a_count_before,
        )


class TenantTeacherIsolationTests(TenantIsolationTestCase):
    def test_teacher_cannot_see_other_school_published_timetable_in_grid(self):
        self.client.login(username=self.school_a.teacher_user.username, password='password')
        response = self.client.get(reverse('timetable:teacher_view'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school_a.subject_code)
        self.assertNotContains(response, self.school_b.subject_code)


class TenantPositiveControlTests(TenantIsolationTestCase):
    def test_school_a_admin_sees_own_timetable_in_teacher_grid(self):
        response = self.client.get(
            reverse('timetable:teacher_view'),
            {'teacher_id': self.school_a.teacher.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school_a.subject_code)
        self.assertGreater(response.context['slot_count'], 0)

    def test_school_a_admin_sees_own_department_in_list(self):
        response = self.client.get(reverse('core:department_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.school_a.department.code)
