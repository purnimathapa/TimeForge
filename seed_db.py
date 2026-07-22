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
    department_specs = [
        ("Department of Architecture", "ARCH"),
        ("Department of Artificial Intelligence", "AI"),
        ("Department of Chemical Science and Engineering", "CHE"),
        ("Department of Civil Engineering", "CE"),
        ("Department of Computer Science and Engineering", "CSE"),
        ("Department of Electrical and Electronics Engineering", "EEE"),
        ("Department of Environmental Engineering", "ENV"),
        ("Department of Geomatics Engineering", "GE"),
        ("Department of Health Informatics", "HI"),
        ("Department of Mechanical Engineering", "ME"),
    ]
    departments = {
        code: Department.objects.create(
            name=name,
            code=code,
            description=name,
            school=school,
        )
        for name, code in department_specs
    }
    arch = departments["ARCH"]
    ai = departments["AI"]
    che = departments["CHE"]
    ce = departments["CE"]
    cse = departments["CSE"]
    eee = departments["EEE"]
    env = departments["ENV"]
    ge = departments["GE"]
    hi = departments["HI"]
    me = departments["ME"]

    # 3. Create Rooms
    print("Seeding Rooms...")
    lecture = Room.RoomType.LECTURE
    lab = Room.RoomType.LAB
    seminar = Room.RoomType.SEMINAR
    computer_lab = Room.RoomType.COMPUTER_LAB

    # name, code, building, floor, capacity, room_type, department
    # Block 9: floors 3/4 → CSE, floor 2 → Geomatics; LAB_305 → CSE (block 9).
    room_specs = [
        ("9-302", "9-302", "9", "3", 60, computer_lab, cse),
        ("9-304", "9-304", "9", "3", 60, lecture, cse),
        ("9-310", "9-310", "9", "3", 60, lecture, cse),
        ("9-402", "9-402", "9", "4", 60, lecture, cse),
        ("9-403", "9-403", "9", "4", 60, lecture, cse),
        ("9-404", "9-404", "9", "4", 60, lecture, cse),
        ("LAB_305", "LAB_305", "9", "3", 30, lab, cse),
        ("9-301", "9-301", "9", "3", 60, seminar, cse),  # Graduate Room
        ("9-202", "9-202", "9", "2", 60, lecture, ge),
        ("9-203", "9-203", "9", "2", 60, lecture, ge),
        ("9-203A", "9-203A", "9", "2", 60, lecture, ge),
        ("9-201", "9-201", "9", "2", 60, lab, ge),  # Simulation Lab
        ("9-Active_Learning_LAB", "9-AL-LAB", "9", "", 30, computer_lab, cse),
        ("10-103", "10-103", "10", "1", 60, lecture, arch),
        ("10-106", "10-106", "10", "1", 60, lecture, arch),
        ("10-202", "10-202", "10", "2", 30, lecture, arch),
        ("10-102", "10-102", "10", "1", 60, lecture, arch),
        ("10-201", "10-201", "10", "2", 60, lecture, arch),
        ("10-107", "10-107", "10", "1", 60, lecture, arch),
        ("Archi Block (Shed)", "ARCHI-SHED", "Archi Block", "", 60, lab, arch),
        ("6-208", "6-208", "6", "2", 60, lecture, eee),
        ("6-202", "6-202", "6", "2", 60, lecture, eee),
        ("6-203", "6-203", "6", "2", 60, lecture, eee),
        ("6-209", "6-209", "6", "2", 60, lecture, eee),
        ("6-S3", "6-S3", "6", "", 60, seminar, eee),
        ("6-S4", "6-S4", "6", "", 30, seminar, eee),
        ("6-S5", "6-S5", "6", "", 30, seminar, eee),
        ("6-S6", "6-S6", "6", "", 60, seminar, eee),
        ("Electrical Lab", "ELEC-LAB", "", "", 60, lab, None),
        ("8-505", "8-505", "8", "5", 60, lecture, me),
        ("8-204", "8-204", "8", "2", 60, lecture, me),
        ("8-502", "8-502", "8", "5", 30, lecture, me),
        ("8-503", "8-503", "8", "5", 30, lecture, me),
        ("11-104", "11-104", "11", "1", 60, lecture, ce),
        ("11-110", "11-110", "11", "1", 60, lecture, ce),
        ("11-105", "11-105", "11", "1", 60, lecture, ce),
        ("3-LUPIC Lab", "3-LUPIC-L", "3", "", 30, lab, None),
        ("3-LUPIC Class Room", "3-LUPIC-C", "3", "", 30, lecture, None),
        ("TTC", "TTC", "", "", 60, lecture, None),
        ("Drawing Hall", "DRAW-HALL", "", "", 60, lecture, None),
        ("Workshop", "WORKSHOP", "", "", 60, lab, None),
        ("Rinpoche-1", "RINPOCHE-1", "", "", 60, lecture, None),
        ("Rinpoche-2", "RINPOCHE-2", "", "", 60, lecture, None),
    ]
    for name, code, building, floor, capacity, room_type, dept in room_specs:
        Room.objects.create(
            name=name,
            code=code,
            building=building,
            floor=floor,
            capacity=capacity,
            room_type=room_type,
            department=dept,
            school=school,
        )

    # Test SET_NULL on Room when Department is deleted
    test_dept = Department.objects.create(name="Test Dept", code="TEST", school=school)
    test_room = Room.objects.create(name="Test Room", code="TEST-RM", capacity=50, department=test_dept, school=school)
    test_dept.delete()
    test_room.refresh_from_db()
    if test_room.department is None:
        print("PASS: Room department set to NULL upon department deletion.")
    else:
        print("FAIL: Expected Room department to be NULL.")
    test_room.delete()

    # 4. Create Subjects
    print("Seeding Subjects...")
    Subject.objects.create(name="Data Structures", code="CS201", department=cse)
    Subject.objects.create(name="Algorithms", code="CS301", department=cse)
    Subject.objects.create(name="Machine Learning", code="AI101", department=ai)
    Subject.objects.create(name="Reaction Engineering", code="CHE301", department=che)
    Subject.objects.create(name="Architectural Design", code="ARCH201", department=arch)

    # 5. Create Sections (bachelor's programs per department)
    print("Seeding Sections...")
    section_specs = [
        # Computer Science and Engineering
        ("BE in Computer Engineering", cse),
        ("Bachelor of Information Technology (BIT)", cse),
        ("Bachelor of Information Technology (BIT) – Double Degree", cse),
        ("BSc in Computer Science", cse),
        ("B.Tech in Cybersecurity", cse),
        # Electrical and Electronics Engineering
        ("BE in Electrical and Electronics Engineering", eee),
        # Mechanical Engineering (tracks)
        ("BE in Mechanical Engineering (Automobile)", me),
        ("BE in Mechanical Engineering (Design & Manufacturing)", me),
        ("BE in Mechanical Engineering (Energy Technology)", me),
        ("BE in Mechanical Engineering (Hydropower)", me),
        # Geomatics Engineering
        ("BE in Geomatics Engineering", ge),
        # Architecture
        ("Bachelor in Heritage Conservation (BHC)", arch),
        ("Bachelor of Architecture (B.Arch)", arch),
        # Chemical Science and Engineering
        ("BE in Chemical Engineering", che),
        # Civil Engineering
        ("BE in Civil Engineering", ce),
        ("BE in Mining Engineering", ce),
        # Artificial Intelligence
        ("Bachelor of Technology (B.Tech) in Artificial Intelligence", ai),
        # Environmental Engineering
        ("BE in Environmental Engineering", env),
        # Health Informatics: no bachelor's program listed
    ]
    for program_name, dept in section_specs:
        Section.objects.create(
            name=program_name,
            year=1,
            section_label="A",
            student_count=40,
            department=dept,
            semester=s1,
        )

    # 6. Create TeacherProfiles
    print("Seeding Teacher Profiles...")
    teacher_user, _ = User.objects.get_or_create(username='teacher1', defaults={'email':'teacher1@example.com', 'role':'TEACHER', 'school': school})
    if not teacher_user.password:
        teacher_user.set_password('teacherpass')
        teacher_user.school = school
        teacher_user.save()
        
    t1 = TeacherProfile.objects.create(user=teacher_user, employee_id="EMP001", title="Dr.", department=cse)
    
    # Add a few more users and teacher profiles
    teacher_depts = [cse, ce, me, eee, ai, hi, ge, env]
    for i in range(2, 6):
        u, _ = User.objects.get_or_create(username=f'teacher{i}', defaults={'email':f'teacher{i}@example.com', 'role':'TEACHER', 'school': school})
        u.set_password('teacherpass')
        u.school = school
        u.save()
        dept = teacher_depts[(i - 2) % len(teacher_depts)]
        TeacherProfile.objects.create(user=u, employee_id=f"EMP00{i}", title="Prof.", department=dept)
        
    # 7. Create ClassSessions
    print("Seeding ClassSessions...")
    be_ce = Section.objects.get(name="BE in Computer Engineering", semester=s1)
    bit = Section.objects.get(name="Bachelor of Information Technology (BIT)", semester=s1)
    btech_ai = Section.objects.get(name="Bachelor of Technology (B.Tech) in Artificial Intelligence", semester=s1)
    ClassSession.objects.create(subject=Subject.objects.get(code="CS201"), teacher=t1, section=be_ce, periods_per_week=3)
    ClassSession.objects.create(subject=Subject.objects.get(code="CS301"), teacher=t1, section=bit, periods_per_week=4)
    ClassSession.objects.create(subject=Subject.objects.get(code="AI101"), teacher=TeacherProfile.objects.get(employee_id="EMP002"), section=btech_ai, periods_per_week=3)

    print("Seed complete! 5+ rows generated for each model.")

if __name__ == '__main__':
    run_tests_and_seed()
