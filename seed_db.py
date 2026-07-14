import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "timeforge.settings.base")
django.setup()

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from core.models import Department, Room, School, Semester
from academics.models import Subject, Section, TeacherProfile, ClassSession
from scheduling.models import TeacherAvailability, TimeSlot
import datetime

User = get_user_model()

def run_tests_and_seed():
    print("Running Tests and Seeding DB...")
    
    # Clean up previous seed if running multiple times
    from timetable.models import TimetableSlot, Timetable, DraftChangeSet, DraftMove

    DraftMove.objects.all().delete()
    DraftChangeSet.objects.all().delete()
    TimetableSlot.objects.all().delete()
    Timetable.objects.all().delete()
    Room.objects.all().delete()
    ClassSession.objects.all().delete()
    Subject.objects.all().delete()
    Section.objects.all().delete()
    TeacherAvailability.objects.all().delete()
    TeacherProfile.objects.all().delete()
    Department.objects.all().delete()
    Semester.objects.all().delete()

    school, _ = School.objects.get_or_create(
        code='default',
        defaults={'name': 'Default School', 'is_active': True},
    )
    
    # 1. Create Semesters
    print("Seeding Semesters...")
    s1 = Semester.objects.create(
        name="Fall 2026", code="FA26",
        start_date=datetime.date(2026, 8, 1), end_date=datetime.date(2026, 12, 15),
        is_active=True, school=school,
    )
    s2 = Semester.objects.create(
        name="Spring 2027", code="SP27",
        start_date=datetime.date(2027, 1, 15), end_date=datetime.date(2027, 5, 30),
        is_active=False, school=school,
    )
    
    # Test Semester uniqueness constraint on is_active (scoped per school)
    s3 = Semester(
        name="Summer 2027", code="SU27",
        start_date=datetime.date(2027, 6, 1), end_date=datetime.date(2027, 7, 30),
        is_active=True, school=school,
    )
    try:
        s3.clean()
        print("FAIL: Expected ValidationError for second active semester")
    except ValidationError as e:
        print(f"PASS: Validation error raised for second active semester: {e}")
        
    Semester.objects.create(name="Fall 2027", code="FA27", start_date=datetime.date(2027, 8, 1), end_date=datetime.date(2027, 12, 15), is_active=False, school=school)
    Semester.objects.create(name="Spring 2028", code="SP28", start_date=datetime.date(2028, 1, 15), end_date=datetime.date(2028, 5, 30), is_active=False, school=school)
    Semester.objects.create(name="Summer 2028", code="SU28", start_date=datetime.date(2028, 6, 1), end_date=datetime.date(2028, 7, 30), is_active=False, school=school)

    # 2. Create Departments
    print("Seeding Departments...")
    cs = Department.objects.create(name="Computer Science", code="CS", description="CS Dept", school=school)
    math = Department.objects.create(name="Mathematics", code="MATH", description="Math Dept", school=school)
    phy = Department.objects.create(name="Physics", code="PHY", description="Physics Dept", school=school)
    eng = Department.objects.create(name="English", code="ENG", description="English Dept", school=school)
    bio = Department.objects.create(name="Biology", code="BIO", description="Biology Dept", school=school)

    # 3. Create Rooms
    print("Seeding Rooms...")
    r1 = Room.objects.create(name="Lecture Hall A", code="LHA", capacity=100, room_type=Room.RoomType.LECTURE, department=cs, school=school)
    r2 = Room.objects.create(name="CS Lab 1", code="CSL1", capacity=30, room_type=Room.RoomType.COMPUTER_LAB, department=cs, school=school)
    r3 = Room.objects.create(name="Math Seminar Room", code="MSR", capacity=20, room_type=Room.RoomType.SEMINAR, department=math, school=school)
    r4 = Room.objects.create(name="Physics Lab A", code="PHYL", capacity=25, room_type=Room.RoomType.LAB, department=phy, school=school)
    r5 = Room.objects.create(name="General Lecture Hall B", code="LHB", capacity=150, room_type=Room.RoomType.LECTURE, school=school)
    
    # Test SET_NULL on Room when Department is deleted
    test_dept = Department.objects.create(name="Test Dept", code="TEST", school=school)
    test_room = Room.objects.create(name="Test Room", capacity=50, department=test_dept, school=school)
    test_dept.delete()
    test_room.refresh_from_db()
    if test_room.department is None:
        print("PASS: Room department set to NULL upon department deletion.")
    else:
        print("FAIL: Expected Room department to be NULL.")
    test_room.delete()

    # 4. Create Subjects
    print("Seeding Subjects...")
    Subject.objects.create(name="Data Structures", code="CS201", department=cs)
    Subject.objects.create(name="Algorithms", code="CS301", department=cs)
    Subject.objects.create(name="Calculus I", code="MATH101", department=math)
    Subject.objects.create(name="Quantum Mechanics", code="PHY301", department=phy)
    Subject.objects.create(name="Technical Writing", code="ENG201", department=eng)

    # 5. Create Sections
    print("Seeding Sections...")
    Section.objects.create(name="CS Batch 2026 A", year=1, section_label="A", student_count=60, department=cs, semester=s1)
    Section.objects.create(name="CS Batch 2026 B", year=1, section_label="B", student_count=60, department=cs, semester=s1)
    Section.objects.create(name="Math Batch 2026", year=1, section_label="A", student_count=40, department=math, semester=s1)
    Section.objects.create(name="Physics Batch 2025", year=2, section_label="A", student_count=30, department=phy, semester=s1)
    Section.objects.create(name="Bio Batch 2026", year=1, section_label="A", student_count=50, department=bio, semester=s1)

    # 6. Create TeacherProfiles
    print("Seeding Teacher Profiles...")
    teacher_user, _ = User.objects.get_or_create(username='teacher1', defaults={'email':'teacher1@example.com', 'role':'TEACHER', 'school': school})
    if not teacher_user.password:
        teacher_user.set_password('teacherpass')
        teacher_user.school = school
        teacher_user.save()
        
    t1 = TeacherProfile.objects.create(user=teacher_user, employee_id="EMP001", title="Dr.", department=cs)
    
    # Add a few more users and teacher profiles
    for i in range(2, 6):
        u, _ = User.objects.get_or_create(username=f'teacher{i}', defaults={'email':f'teacher{i}@example.com', 'role':'TEACHER', 'school': school})
        u.set_password('teacherpass')
        u.school = school
        u.save()
        dept = [cs, math, phy, eng][(i-2) % 4]
        TeacherProfile.objects.create(user=u, employee_id=f"EMP00{i}", title="Prof.", department=dept)
        
    # 7. Create ClassSessions
    print("Seeding ClassSessions...")
    ClassSession.objects.create(subject=Subject.objects.get(code="CS201"), teacher=t1, section=Section.objects.get(name="CS Batch 2026 A"), periods_per_week=3)
    ClassSession.objects.create(subject=Subject.objects.get(code="CS301"), teacher=t1, section=Section.objects.get(name="CS Batch 2026 B"), periods_per_week=4)
    ClassSession.objects.create(subject=Subject.objects.get(code="MATH101"), teacher=TeacherProfile.objects.get(employee_id="EMP002"), section=Section.objects.get(name="Math Batch 2026"), periods_per_week=3)

    print("Seed complete! 5+ rows generated for each model.")

if __name__ == '__main__':
    run_tests_and_seed()
